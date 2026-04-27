"""
report_generator.py — HTML + JSON Report Builder

Generates a rich, self-contained HTML report and a machine-readable
JSON report from the GateDecision and raw test results.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chaos_runner.config_loader import ChaosConfig
    from chaos_runner.threshold_evaluator import GateDecision
    from chaos_runner.test_executor import TestResult

# ── HTML Template ──────────────────────────────────────────────────────────────

_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Chaos Report — {project}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  :root {{ --pass:#22c55e;--fail:#ef4444;--warn:#f59e0b;--error:#8b5cf6;--bg:#0f172a;--card:#1e293b;--border:#334155;--text:#e2e8f0;--accent:#38bdf8; }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ font-family:'Inter',sans-serif; background:var(--bg); color:var(--text); padding:2rem; font-size:14px; }}
  h1 {{ font-size:2rem; font-weight:700; }}
  h2 {{ font-size:1.2rem; font-weight:600; color:var(--accent); margin-bottom:1rem; }}
  h3 {{ font-size:1rem; font-weight:600; margin-bottom:.5rem; }}
  .banner {{ border-radius:12px; padding:2rem; margin-bottom:2rem; text-align:center; }}
  .banner.pass {{ background:linear-gradient(135deg,#064e3b,#065f46); border:2px solid var(--pass); }}
  .banner.fail {{ background:linear-gradient(135deg,#450a0a,#7f1d1d); border:2px solid var(--fail); }}
  .banner h1 {{ font-size:2.5rem; margin-bottom:.5rem; }}
  .banner .meta {{ opacity:.7; font-size:.9rem; }}
  .card {{ background:var(--card); border:1px solid var(--border); border-radius:10px; padding:1.5rem; margin-bottom:1.5rem; }}
  table {{ width:100%; border-collapse:collapse; }}
  th {{ text-align:left; padding:.6rem .8rem; font-size:.8rem; letter-spacing:.05em; text-transform:uppercase; color:#94a3b8; border-bottom:1px solid var(--border); }}
  td {{ padding:.6rem .8rem; border-bottom:1px solid #1e293b; vertical-align:top; }}
  tr:last-child td {{ border-bottom:none; }}
  .badge {{ display:inline-block; padding:.15rem .5rem; border-radius:4px; font-size:.75rem; font-weight:700; }}
  .badge.pass {{ background:#14532d; color:var(--pass); }}
  .badge.fail {{ background:#450a0a; color:var(--fail); }}
  .badge.warn {{ background:#451a03; color:var(--warn); }}
  .badge.error {{ background:#2e1065; color:var(--error); }}
  .ai-box {{ white-space:pre-wrap; line-height:1.7; font-size:.9rem; }}
  .mono {{ font-family:monospace; font-size:.85rem; color:#7dd3fc; }}
  details summary {{ cursor:pointer; color:var(--accent); font-size:.85rem; }}
  details pre {{ margin-top:.5rem; background:#0f172a; padding:.75rem; border-radius:6px; overflow-x:auto; font-size:.8rem; }}
  .grid-3 {{ display:grid; grid-template-columns:repeat(3,1fr); gap:1rem; margin-bottom:1.5rem; }}
  .stat {{ background:var(--card); border:1px solid var(--border); border-radius:10px; padding:1.25rem; text-align:center; }}
  .stat .num {{ font-size:2.5rem; font-weight:700; }}
  .stat .lbl {{ font-size:.8rem; opacity:.6; margin-top:.25rem; }}
  .reasons {{ margin-top:.4rem; padding-left:1rem; color:#f87171; font-size:.85rem; }}
  .reasons li {{ margin-bottom:.2rem; }}
</style>
</head>
<body>

<div class="banner {banner_cls}">
  <h1>{banner_icon} {banner_text}</h1>
  <div class="meta">{project} &middot; {timestamp} &middot; {total_tests} tests executed</div>
</div>

<div class="grid-3">
  <div class="stat"><div class="num" style="color:var(--pass)">{passed}</div><div class="lbl">PASSED</div></div>
  <div class="stat"><div class="num" style="color:var(--fail)">{failed}</div><div class="lbl">FAILED</div></div>
  <div class="stat"><div class="num" style="color:var(--warn)">{warned}</div><div class="lbl">WARNINGS</div></div>
</div>

{ai_section}

<div class="card">
  <h2>📊 Test Results</h2>
  <table>
    <thead><tr><th>Test ID</th><th>Type</th><th>Target</th><th>Status</th><th>Latency Regression</th><th>5xx Rate</th><th>Issues</th></tr></thead>
    <tbody>
      {rows}
    </tbody>
  </table>
</div>

{detail_sections}

</body></html>"""

_ROW = """<tr>
  <td class="mono">{id}</td>
  <td>{type}</td>
  <td>{target}</td>
  <td><span class="badge {cls}">{icon} {status}</span></td>
  <td>{regression}</td>
  <td>{rate5xx}</td>
  <td>{issues}</td>
</tr>"""

_DETAIL = """<div class="card">
  <h2>🔬 {id} — {type} on {target}</h2>
  <div style="opacity:.7;margin-bottom:1rem">Duration: {duration}s &middot; Verdict: <span class="badge {cls}">{status}</span></div>
  {content}
</div>"""


# ── Helpers ────────────────────────────────────────────────────────────────────

def _badge_cls(status: str) -> str:
    return {"PASS": "pass", "FAIL": "fail", "WARN": "warn", "ERROR": "error"}.get(status, "warn")


def _phase_table(rows: list, label: str) -> str:
    if not rows:
        return ""
    header = f"<h3>{label}</h3>"
    trs = "".join(
        f"<tr><td>{r.get('request','?')}</td>"
        f"<td class='mono'>{r.get('latency','?')}s</td>"
        f"<td>{r.get('status','?')}</td></tr>"
        for r in rows
    )
    return f"{header}<table><thead><tr><th>Req</th><th>Latency</th><th>Status</th></tr></thead><tbody>{trs}</tbody></table><br>"


def _payload_table(rows: list) -> str:
    if not rows:
        return "<p style='opacity:.7'>No payload results.</p>"
    trs = ""
    for r in rows:
        body = r.get("request_body")
        body_html = ""
        if body:
            body_str = json.dumps(body, indent=2) if isinstance(body, dict) else str(body)
            # Truncate huge payloads for readability
            if len(body_str) > 500:
                body_str = body_str[:500] + "\n... [truncated]"
            body_html = f"<details><summary>View Payload</summary><pre>{body_str}</pre></details>"
        st = r.get("status", "?")
        cls = "fail" if st in ("timeout_or_error", "timeout") or (isinstance(st, int) and st >= 500) else ""
        trs += (
            f"<tr class='{cls}'>"
            f"<td class='mono'>{r.get('payload_name','?')}{body_html}</td>"
            f"<td>{r.get('description','?')}</td>"
            f"<td class='mono'>{r.get('latency','?')}ms</td>"
            f"<td>{st}</td></tr>"
        )
    return (
        "<table><thead><tr><th>Payload</th><th>Target / Desc</th>"
        "<th>Latency</th><th>Status</th></tr></thead>"
        f"<tbody>{trs}</tbody></table>"
    )


# ── Public API ─────────────────────────────────────────────────────────────────

def generate(
    config: "ChaosConfig",
    gate: "GateDecision",
    results: list["TestResult"],
    ai_verdict: str,
) -> tuple[str, dict]:
    """Return (html_string, json_dict)."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    is_pass = gate.is_pass

    # Summary counts
    passed = sum(1 for v in gate.verdicts if v.status == "PASS")
    failed = sum(1 for v in gate.verdicts if v.status in ("FAIL", "ERROR"))
    warned = sum(1 for v in gate.verdicts if v.status == "WARN")

    # Table rows
    rows = ""
    for v in gate.verdicts:
        cls = _badge_cls(v.status)
        issues_html = ""
        if v.reasons:
            items = "".join(f"<li>{r}</li>" for r in v.reasons)
            issues_html = f"<ul class='reasons'>{items}</ul>"
        rows += _ROW.format(
            id=v.test_id,
            type=v.test_type,
            target=v.target,
            cls=cls,
            icon=v.status_icon,
            status=v.status,
            regression=f"{v.latency_regression_pct}%" if v.latency_regression_pct is not None else "—",
            rate5xx=f"{v.payload_5xx_rate}%" if v.payload_5xx_rate else "—",
            issues=issues_html or "—",
        )

    # Per-test detail sections
    result_map = {r.test_id: r for r in results}
    detail_sections = ""
    for v in gate.verdicts:
        r = result_map.get(v.test_id)
        if not r or not r.raw:
            continue
        raw = r.raw
        content = ""
        if v.test_type == "payload":
            content += "<h3>🔒 Security Vulnerability Scan</h3>" + _payload_table(raw.get("payload_results", []))
            content += "<br><h3>💥 Degradation Bombing</h3>"
            content += _phase_table(raw.get("baseline", []), "Baseline")
            content += _phase_table(raw.get("during_fault", []), "During Fault")
            content += _phase_table(raw.get("post_recovery", []), "Post Recovery")
        else:
            content += _phase_table(raw.get("baseline", []), "Baseline")
            content += _phase_table(raw.get("during_fault", []), "During Fault")
            content += _phase_table(raw.get("post_recovery", []), "Post Recovery")

        detail_sections += _DETAIL.format(
            id=v.test_id,
            type=v.test_type,
            target=v.target,
            duration=v.duration_s,
            cls=_badge_cls(v.status),
            status=v.status,
            content=content,
        )

    # AI section
    ai_html = ""
    if ai_verdict:
        import re
        # Convert markdown to basic HTML
        ai_formatted = (
            ai_verdict
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("**", "<strong>", 1)
        )
        # Simple markdown → html
        ai_formatted = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", ai_verdict)
        ai_formatted = re.sub(r"### (.+)", r"<h3>\1</h3>", ai_formatted)
        ai_formatted = re.sub(r"- ", r"• ", ai_formatted)
        ai_html = f'<div class="card"><h2>🤖 AI Production Verdict</h2><div class="ai-box">{ai_formatted}</div></div>'

    html = _HTML.format(
        project=config.project,
        timestamp=timestamp,
        total_tests=len(gate.verdicts),
        banner_cls="pass" if is_pass else "fail",
        banner_icon="✅" if is_pass else "❌",
        banner_text=gate.banner.replace("✅  ", "").replace("❌  ", ""),
        passed=passed,
        failed=failed,
        warned=warned,
        ai_section=ai_html,
        rows=rows,
        detail_sections=detail_sections,
    )

    json_report = {
        "project": config.project,
        "timestamp": timestamp,
        "overall": gate.overall,
        "verdicts": [
            {
                "test_id": v.test_id,
                "type": v.test_type,
                "target": v.target,
                "status": v.status,
                "on_fail": v.on_fail,
                "reasons": v.reasons,
                "latency_regression_pct": v.latency_regression_pct,
                "payload_5xx_rate": v.payload_5xx_rate,
                "payload_crash_rate": v.payload_crash_rate,
                "duration_s": v.duration_s,
            }
            for v in gate.verdicts
        ],
        "ai_verdict": ai_verdict,
    }

    return html, json_report


def write_reports(
    html: str,
    json_report: dict,
    html_path: str,
    json_path: str,
) -> None:
    Path(html_path).write_text(html, encoding="utf-8")
    Path(json_path).write_text(json.dumps(json_report, indent=2), encoding="utf-8")
