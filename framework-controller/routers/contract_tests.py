"""
Contract Tests Router — OpenAPI-driven payload resilience testing.

Endpoints:
- POST /contract/discover  → discover OpenAPI docs for running compose services
- POST /contract/payload   → run payload resilience suite against a selected OpenAPI spec
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.docker_manager import discover_services


router = APIRouter(prefix="/contract", tags=["Contract Tests"])

RESULTS_FILE = "experiment_results.json"


def _save_entry(entry: dict):
    history = []
    if os.path.exists(RESULTS_FILE):
        try:
            with open(RESULTS_FILE, "r") as f:
                data = json.load(f)
                history = data if isinstance(data, list) else [data]
        except (json.JSONDecodeError, IOError):
            history = []
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    history.append(entry)
    with open(RESULTS_FILE, "w") as f:
        json.dump(history, f, indent=4)


def _is_docker() -> bool:
    return os.path.exists("/.dockerenv")


def _first_port(ports: dict) -> Optional[tuple[str, str]]:
    """
    Return (container_port, mapped_port) from docker_manager ports dict,
    where keys are like '8000/tcp' and values are host port strings.
    """
    if not isinstance(ports, dict) or not ports:
        return None
    k = next(iter(ports.keys()))
    return k, ports.get(k)


class DiscoverRequest(BaseModel):
    project: Optional[str] = None
    openapi_path: Optional[str] = "/openapi.json"
    timeout_s: Optional[float] = 2.5


@router.post("/discover")
async def discover_openapi(req: DiscoverRequest):
    """
    Attempt to locate OpenAPI specs for all discovered Docker Compose services.

    Returns a list of candidates with computed openapi_url and base_url.
    """
    import httpx

    services = discover_services(project=req.project)
    is_docker = _is_docker()
    out = []

    async with httpx.AsyncClient(timeout=req.timeout_s, follow_redirects=True) as client:
        for svc in services:
            if svc["status"] != "running":
                continue

            p = _first_port(svc.get("ports") or {})
            if not p:
                continue

            container_port, mapped_port = p
            internal_port = container_port.split("/")[0]

            host = svc["container_name"] if is_docker else "localhost"
            port = internal_port if is_docker else mapped_port
            if not port:
                continue

            base_url = f"http://{host}:{port}"
            openapi_url = f"{base_url}{req.openapi_path}"

            ok = False
            title = None
            try:
                r = await client.get(openapi_url)
                if r.status_code == 200:
                    doc = r.json()
                    title = (doc.get("info") or {}).get("title")
                    ok = True
            except Exception:
                ok = False

            out.append(
                {
                    "service": svc["name"],
                    "container_name": svc["container_name"],
                    "project": svc["project"],
                    "base_url": base_url,
                    "openapi_url": openapi_url,
                    "openapi_ok": ok,
                    "title": title,
                }
            )

    return {"services": out, "is_docker": is_docker}


class PayloadTestRequest(BaseModel):
    openapi_url: str
    base_url: Optional[str] = None
    bearer_token: Optional[str] = None
    modes: Optional[list[str]] = ["payload", "params"]
    include_path_regex: Optional[str] = ".*"
    max_operations: Optional[int] = 10
    max_cases_per_operation: Optional[int] = 10
    concurrency: Optional[int] = 8
    request_timeout_s: Optional[float] = 10.0
    seed: Optional[int] = 1337


@router.post("/payload")
async def run_payload_tests(req: PayloadTestRequest):
    """
    Run payload resilience tests against endpoints described by OpenAPI.
    """
    from services.openapi_fuzzer import run_payload_resilience_suite

    if not req.openapi_url.startswith("http"):
        raise HTTPException(status_code=400, detail="openapi_url must be an http(s) URL")

    base_url = req.base_url or req.openapi_url.rsplit("/", 1)[0]

    try:
        suite = await run_payload_resilience_suite(
            openapi_url=req.openapi_url,
            base_url=base_url,
            bearer_token=req.bearer_token,
            modes=req.modes,
            include_path_regex=req.include_path_regex or ".*",
            max_operations=int(req.max_operations or 10),
            max_cases_per_operation=int(req.max_cases_per_operation or 10),
            concurrency=int(req.concurrency or 8),
            request_timeout_s=float(req.request_timeout_s or 10.0),
            seed=int(req.seed or 1337),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Payload test failed: {str(e)}")

    entry = {
        "source": "contract_payload",
        "test_type": "payload_resilience",
        "openapi_url": suite.get("openapi_url"),
        "base_url": suite.get("base_url"),
        "summary": suite.get("summary"),
        "elapsed_s": suite.get("elapsed_s"),
    }
    _save_entry(entry)

    return suite

