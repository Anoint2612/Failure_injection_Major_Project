"""
OpenAPI Fuzzer — contract-driven payload resilience tests.

Goal:
- Given a service OpenAPI document, generate a small suite of valid and invalid
  JSON payloads for write endpoints (POST/PUT/PATCH).
- Execute the requests with bounded concurrency.
- Return a compact, structured result suitable for persistence + AI analysis.

This intentionally avoids deep schema support (oneOf/allOf, refs across files, etc.)
and focuses on practical "does it fail safely?" checks that work across most REST APIs.
"""

from __future__ import annotations

import asyncio
import json
import random
import re
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx


def _is_docker() -> bool:
    import os

    return os.path.exists("/.dockerenv")


def _safe_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return {"_raw": resp.text[:2000]}


def _deref(schema: dict, doc: dict) -> dict:
    """
    Resolve a *local* $ref in the same OpenAPI doc (e.g. '#/components/schemas/Foo').
    Best-effort only — if unsupported, returns the original schema.
    """
    if not isinstance(schema, dict):
        return schema

    ref = schema.get("$ref")
    if not ref or not isinstance(ref, str) or not ref.startswith("#/"):
        return schema

    parts = [p for p in ref.lstrip("#/").split("/") if p]
    cur: Any = doc
    try:
        for p in parts:
            cur = cur[p]
        if isinstance(cur, dict):
            merged = dict(cur)
            merged.update({k: v for k, v in schema.items() if k != "$ref"})
            return merged
    except Exception:
        return schema
    return schema


def _pick_content_schema(operation: dict, doc: dict) -> Optional[dict]:
    request_body = operation.get("requestBody") or {}
    content = request_body.get("content") or {}
    app_json = content.get("application/json") or content.get("application/*+json")
    if not isinstance(app_json, dict):
        return None
    schema = app_json.get("schema")
    if not isinstance(schema, dict):
        return None
    schema = _deref(schema, doc)
    return schema


def _example_for_schema(schema: dict, doc: dict, depth: int = 0) -> Any:
    """
    Create a small "valid-looking" example for a JSON schema fragment.
    Handles common OpenAPI schema subsets: type/object/array/enum/format.
    """
    if depth > 6:
        return None

    schema = _deref(schema, doc) if isinstance(schema, dict) else {}

    if "enum" in schema and isinstance(schema["enum"], list) and schema["enum"]:
        return schema["enum"][0]

    t = schema.get("type")
    if t == "string":
        fmt = schema.get("format")
        if fmt == "email":
            return "user@example.com"
        if fmt in ("uuid", "uuid4"):
            return "00000000-0000-0000-0000-000000000000"
        if fmt in ("date-time", "datetime"):
            return "2026-01-01T00:00:00Z"
        if fmt == "date":
            return "2026-01-01"
        min_len = int(schema.get("minLength") or 1)
        return "a" * max(min_len, 1)

    if t == "integer":
        return int(schema.get("minimum") or 1)

    if t == "number":
        return float(schema.get("minimum") or 1.0)

    if t == "boolean":
        return True

    if t == "array":
        items = schema.get("items") or {}
        items = _deref(items, doc) if isinstance(items, dict) else {}
        min_items = int(schema.get("minItems") or 1)
        return [_example_for_schema(items, doc, depth + 1) for _ in range(max(min_items, 1))]

    # object or unspecified defaults to object if properties exist
    if t == "object" or "properties" in schema:
        props = schema.get("properties") or {}
        required = schema.get("required") or []
        out = {}
        if isinstance(props, dict):
            for key, prop_schema in props.items():
                if key in required:
                    out[key] = _example_for_schema(prop_schema or {}, doc, depth + 1)
        # If no required fields, still include 1 property for "shape"
        if not out and isinstance(props, dict) and props:
            k = next(iter(props.keys()))
            out[k] = _example_for_schema(props[k] or {}, doc, depth + 1)
        return out

    # Fallback
    return None


def _mutations_for_payload(payload: Any, schema: dict) -> list[dict]:
    """
    Produce a small set of "bad" payload variants.
    This is intentionally generic and doesn’t try to be exhaustive.
    """
    muts: list[dict] = []

    # Malformed JSON is tested by sending an invalid body string (handled in runner)
    # so here we focus on schema-breaking JSON values.

    # null body
    muts.append({"kind": "null_body", "body": None})

    # wrong root type
    if isinstance(payload, dict):
        muts.append({"kind": "wrong_root_type", "body": "not-an-object"})
        # remove a required-like key (best-effort from schema)
        req = schema.get("required") if isinstance(schema, dict) else None
        if isinstance(req, list) and req:
            key = req[0]
            if key in payload:
                bad = dict(payload)
                bad.pop(key, None)
                muts.append({"kind": "missing_required_field", "body": bad, "meta": {"missing": key}})
        # add unexpected field
        bad2 = dict(payload)
        bad2["__unexpected__"] = "x"
        muts.append({"kind": "extra_field", "body": bad2})

        # string field mutations (oversize, sqli, xss)
        for k, v in payload.items():
            if isinstance(v, str):
                bad3 = dict(payload)
                bad3[k] = "A" * 20000
                muts.append({"kind": "oversize_string", "body": bad3, "meta": {"field": k, "len": 20000}})
                
                bad_sqli = dict(payload)
                bad_sqli[k] = "admin' OR 1=1--"
                muts.append({"kind": "sql_injection", "body": bad_sqli, "meta": {"field": k}})
                
                bad_xss = dict(payload)
                bad_xss[k] = "<script>alert(1)</script>"
                muts.append({"kind": "xss", "body": bad_xss, "meta": {"field": k}})
                break

        # type confusion in first numeric field
        for k, v in payload.items():
            if isinstance(v, (int, float)):
                bad4 = dict(payload)
                bad4[k] = "999999999999999999999"
                muts.append({"kind": "type_confusion_number_to_string", "body": bad4, "meta": {"field": k}})
                break

    elif isinstance(payload, list):
        muts.append({"kind": "wrong_root_type", "body": {"not": "an-array"}})
        muts.append({"kind": "oversize_array", "body": payload * 500})
    else:
        muts.append({"kind": "wrong_root_type", "body": {"wrapped": payload}})

    # Cap to keep tests bounded
    return muts[:8]


@dataclass
class OperationTarget:
    method: str
    path: str
    operation_id: str
    has_json_body: bool


def _iter_operations(openapi: dict):
    paths = openapi.get("paths") or {}
    if not isinstance(paths, dict):
        return

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method in ("get", "post", "put", "patch", "delete"):
            op = path_item.get(method)
            if not isinstance(op, dict):
                continue
            op_id = op.get("operationId") or f"{method.upper()} {path}"
            schema = _pick_content_schema(op, openapi)
            yield path, method.upper(), op, str(op_id), bool(schema)


def list_write_operations(openapi: dict) -> list[OperationTarget]:
    """
    Extract write operations (POST/PUT/PATCH) that accept application/json bodies.
    """
    out: list[OperationTarget] = []
    for path, method, _op, op_id, has_json_body in _iter_operations(openapi):
        if method not in ("POST", "PUT", "PATCH"):
            continue
        if not has_json_body:
            continue
        out.append(
            OperationTarget(
                method=method,
                path=path,
                operation_id=op_id,
                has_json_body=True,
            )
        )
    return out


def list_all_operations(openapi: dict) -> list[OperationTarget]:
    out: list[OperationTarget] = []
    for path, method, _op, op_id, has_json_body in _iter_operations(openapi):
        out.append(
            OperationTarget(
                method=method,
                path=path,
                operation_id=op_id,
                has_json_body=has_json_body,
            )
        )
    return out


async def fetch_openapi(openapi_url: str, timeout_s: float = 5.0) -> dict:
    async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
        resp = await client.get(openapi_url)
        resp.raise_for_status()
        return resp.json()


def _base_url_from_openapi(openapi: dict, fallback: str) -> str:
    servers = openapi.get("servers")
    if isinstance(servers, list) and servers:
        url = servers[0].get("url")
        if isinstance(url, str) and url.startswith("http"):
            return url.rstrip("/")
    return fallback.rstrip("/")


async def run_payload_resilience_suite(
    *,
    openapi_url: str,
    base_url: str,
    bearer_token: Optional[str] = None,
    modes: Optional[list[str]] = None,  # ["payload", "params"]
    include_path_regex: str = ".*",
    max_operations: int = 10,
    max_cases_per_operation: int = 10,
    concurrency: int = 8,
    request_timeout_s: float = 10.0,
    seed: int = 1337,
) -> dict:
    """
    Execute payload resilience tests for a service contract.
    """
    random.seed(seed)
    started = time.time()

    openapi = await fetch_openapi(openapi_url)
    base = _base_url_from_openapi(openapi, base_url)

    modes = modes or ["payload", "params"]
    modes = [m for m in modes if m in ("payload", "params")]
    if not modes:
        modes = ["payload", "params"]

    ops = list_write_operations(openapi) if "payload" in modes else []
    param_ops = list_all_operations(openapi) if "params" in modes else []
    rx = re.compile(include_path_regex)
    ops = [o for o in ops if rx.search(o.path)]
    ops = ops[: max_operations]
    param_ops = [o for o in param_ops if rx.search(o.path)]
    param_ops = param_ops[: max_operations]

    sem = asyncio.Semaphore(max(1, int(concurrency)))
    results: list[dict] = []

    async with httpx.AsyncClient(timeout=request_timeout_s, follow_redirects=True) as client:
        def _headers(extra: Optional[dict] = None) -> dict:
            h = {}
            if bearer_token:
                h["Authorization"] = f"Bearer {bearer_token}"
            if extra:
                h.update(extra)
            return h

        async def run_one_case(
            op: OperationTarget,
            kind: str,
            *,
            url_path: str,
            body: Any = None,
            malformed_json: bool = False,
            query: Optional[dict] = None,
            headers_extra: Optional[dict] = None,
        ) -> dict:
            url = f"{base}{url_path}"
            headers = _headers(headers_extra)
            if op.has_json_body:
                headers.setdefault("Content-Type", "application/json")
            t0 = time.time()
            async with sem:
                try:
                    if malformed_json:
                        resp = await client.request(op.method, url, content=b"{not:json", headers=headers, params=query)
                    else:
                        resp = await client.request(op.method, url, json=body, headers=headers, params=query)
                    latency = round(time.time() - t0, 3)
                    return {
                        "operation_id": op.operation_id,
                        "method": op.method,
                        "path": op.path,
                        "kind": kind,
                        "latency": latency,
                        "status": resp.status_code,
                        "response": _safe_json(resp),
                        "request_body": "{not:json" if malformed_json else body,
                    }
                except Exception as e:
                    latency = round(time.time() - t0, 3)
                    return {
                        "operation_id": op.operation_id,
                        "method": op.method,
                        "path": op.path,
                        "kind": kind,
                        "latency": latency,
                        "status": "timeout",
                        "error": str(e),
                        "request_body": "{not:json" if malformed_json else body,
                    }

        # --- Payload suite (JSON bodies) ---
        if "payload" in modes:
            for op in ops:
                path_item = openapi.get("paths", {}).get(op.path, {})
                operation = (path_item or {}).get(op.method.lower(), {}) if isinstance(path_item, dict) else {}
                schema = _pick_content_schema(operation, openapi) or {}
                payload = _example_for_schema(schema, openapi)

                cases: list[tuple[str, Any, bool]] = []
                cases.append(("valid_example", payload, False))
                cases.append(("malformed_json", payload, True))

                for m in _mutations_for_payload(payload, schema):
                    cases.append((m["kind"], m.get("body"), False))

                cases = cases[: max_cases_per_operation]
                op_runs = await asyncio.gather(
                    *[
                        run_one_case(op, k, url_path=op.path, body=b, malformed_json=bad)
                        for (k, b, bad) in cases
                    ]
                )
                results.extend(op_runs)

        # --- Parameter abuse suite (query/header/path) ---
        if "params" in modes:
            for op in param_ops:
                path_item = openapi.get("paths", {}).get(op.path, {})
                operation = (path_item or {}).get(op.method.lower(), {}) if isinstance(path_item, dict) else {}
                parameters = []
                if isinstance(path_item, dict) and isinstance(path_item.get("parameters"), list):
                    parameters.extend(path_item.get("parameters") or [])
                if isinstance(operation.get("parameters"), list):
                    parameters.extend(operation.get("parameters") or [])

                # Basic path param substitution
                path_cases = []
                templ = op.path
                path_params = [p for p in parameters if isinstance(p, dict) and p.get("in") == "path"]
                if path_params:
                    # fill all placeholders with "valid-ish"
                    filled = templ
                    for p in path_params:
                        name = p.get("name")
                        if not name:
                            continue
                        filled = filled.replace("{" + name + "}", "1")
                    path_cases.append(("path_validish", filled))
                    # now make one placeholder invalid
                    bad = templ
                    first = path_params[0].get("name")
                    if first:
                        bad = bad.replace("{" + first + "}", "not-a-uuid")
                        for p in path_params[1:]:
                            n = p.get("name")
                            if n:
                                bad = bad.replace("{" + n + "}", "1")
                        path_cases.append(("path_invalid", bad))
                else:
                    path_cases.append(("path_none", templ))

                query_params = [p for p in parameters if isinstance(p, dict) and p.get("in") == "query"]
                header_params = [p for p in parameters if isinstance(p, dict) and p.get("in") == "header"]

                # Build a few query/header abuse variants
                query_variants = [{"kind": "query_none", "query": {}}]
                if query_params:
                    qp = query_params[0]
                    n = qp.get("name") or "q"
                    query_variants.extend(
                        [
                            {"kind": "query_wrong_type", "query": {n: "abc"}},
                            {"kind": "query_oversize", "query": {n: "A" * 20000}},
                            {"kind": "query_duplicate_like", "query": {n: "1,2,3"}},
                        ]
                    )

                header_variants = [{"kind": "header_none", "headers": {}}]
                if header_params:
                    hp = header_params[0]
                    hn = hp.get("name") or "X-Test"
                    header_variants.extend(
                        [
                            {"kind": "header_oversize", "headers": {hn: "B" * 20000}},
                            {"kind": "header_weird_content_type", "headers": {"Content-Type": "text/plain"}},
                            {"kind": "header_accept_weird", "headers": {"Accept": "application/this-does-not-exist"}},
                        ]
                    )
                else:
                    header_variants.extend(
                        [
                            {"kind": "header_weird_content_type", "headers": {"Content-Type": "text/plain"}},
                            {"kind": "header_accept_weird", "headers": {"Accept": "application/this-does-not-exist"}},
                        ]
                    )

                # Execute small cartesian product bounded
                combos = []
                for pk, ppath in path_cases:
                    for qv in query_variants[:3]:
                        for hv in header_variants[:3]:
                            combos.append((f"params:{pk}:{qv['kind']}:{hv['kind']}", ppath, qv["query"], hv["headers"]))
                combos = combos[: max_cases_per_operation]

                op_runs = await asyncio.gather(
                    *[
                        run_one_case(
                            op,
                            kind,
                            url_path=ppath,
                            body=None,
                            malformed_json=False,
                            query=query,
                            headers_extra=headers,
                        )
                        for (kind, ppath, query, headers) in combos
                    ]
                )
                results.extend(op_runs)

    # Summarize
    counts = {"2xx": 0, "4xx": 0, "5xx": 0, "timeout": 0, "other": 0}
    latencies = []
    for r in results:
        st = r.get("status")
        if isinstance(st, int):
            if 200 <= st <= 299:
                counts["2xx"] += 1
            elif 400 <= st <= 499:
                counts["4xx"] += 1
            elif 500 <= st <= 599:
                counts["5xx"] += 1
            else:
                counts["other"] += 1
        elif st == "timeout":
            counts["timeout"] += 1
        else:
            counts["other"] += 1

        if isinstance(r.get("latency"), (int, float)):
            latencies.append(float(r["latency"]))

    latencies.sort()
    def pct(p: float) -> Optional[float]:
        if not latencies:
            return None
        idx = int(round((p / 100.0) * (len(latencies) - 1)))
        return float(latencies[max(0, min(idx, len(latencies) - 1))])

    return {
        "openapi_url": openapi_url,
        "base_url": base,
        "modes": modes,
        "summary": {
            "operations_tested": (len(ops) if "payload" in modes else 0) + (len(param_ops) if "params" in modes else 0),
            "cases_executed": len(results),
            "status_counts": counts,
            "latency_p50": pct(50),
            "latency_p95": pct(95),
        },
        "results": results,
        "elapsed_s": round(time.time() - started, 3),
    }

