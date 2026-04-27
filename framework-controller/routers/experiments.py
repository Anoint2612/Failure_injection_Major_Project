"""
Experiments Router — parameterized chaos experiments.

The frontend provides all parameters (target service, probe URL, fault type)
so the controller never makes assumptions about the target application.
"""

import json
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from services.experiment_runner import run_latency_test, run_stress_test, run_payload_test

router = APIRouter(prefix="/experiment", tags=["Experiments"])

RESULTS_FILE = "experiment_results.json"


def _load_history() -> list:
    """Load the experiment history from disk."""
    if os.path.exists(RESULTS_FILE):
        try:
            with open(RESULTS_FILE, "r") as f:
                data = json.load(f)
                # Handle legacy format (single dict) by wrapping in list
                if isinstance(data, dict):
                    return [data]
                return data
        except (json.JSONDecodeError, IOError):
            return []
    return []


def _save_entry(entry: dict):
    """Append a timestamped entry to experiment history."""
    history = _load_history()
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    history.append(entry)
    with open(RESULTS_FILE, "w") as f:
        json.dump(history, f, indent=4)


class ExperimentRequest(BaseModel):
    """Schema for experiment run requests — fully parameterized."""
    target_service: str
    probe_url: str
    fault_type: str  # "latency" or "stress"
    project: Optional[str] = None
    delay_ms: Optional[int] = 3000
    cpu: Optional[int] = 2
    stress_timeout: Optional[int] = 20
    num_requests: Optional[int] = 5
    bearer_token: Optional[str] = None


@router.post("/run")
async def run_experiment(req: ExperimentRequest):
    """
    Run a parameterized chaos experiment.

    Accepts the target service, a URL to probe for measuring impact,
    the fault type, and fault-specific parameters. Returns measured
    latency data across 3 phases: baseline, during_fault, post_recovery.
    """
    if req.fault_type == "latency":
        results = await run_latency_test(
            target_service=req.target_service,
            probe_url=req.probe_url,
            delay_ms=req.delay_ms,
            num_requests=req.num_requests,
            project=req.project,
        )
    elif req.fault_type == "stress":
        results = await run_stress_test(
            target_service=req.target_service,
            probe_url=req.probe_url,
            cpu=req.cpu,
            stress_timeout=req.stress_timeout,
            num_requests=req.num_requests,
            project=req.project,
        )
    elif req.fault_type == "payload":
        results = await run_payload_test(
            target_service=req.target_service,
            probe_url=req.probe_url,
            project=req.project,
            bearer_token=req.bearer_token,
        )
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown fault type: '{req.fault_type}'. Use 'latency', 'stress', or 'payload'.",
        )

    # Add test type to the result
    results["test_type"] = req.fault_type
    results["source"] = "experiment"

    # Persist results for later retrieval / AI analysis
    _save_entry(results)

    return results


@router.get("/results")
def get_results():
    """Return all saved experiment results."""
    history = _load_history()
    if not history:
        raise HTTPException(
            status_code=404,
            detail="No experiment results found. Run an experiment first.",
        )
    return history


@router.post("/analyze")
def analyze_experiment(data: dict):
    """
    Pass experiment results to Gemini AI to get a Root Cause Analysis
    and remediation report.
    """
    from ai_analyst import analyze_results
    try:
        report = analyze_results(data)
        return {"report": report}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"AI Analysis failed. Check if GEMINI_API_KEY is configured. Error: {str(e)}"
        )


def _get_architecture() -> str:
    """Load the target application architecture from docker-compose.yml or live Docker state."""
    compose_paths = [
        "../target-app/docker-compose.yml",
        "/app/../target-app/docker-compose.yml",
    ]
    for path in compose_paths:
        if os.path.exists(path):
            with open(path, "r") as f:
                return f.read()

    # Fallback: build architecture from live Docker state
    from services.docker_manager import discover_services
    services = discover_services()
    arch_lines = ["# Live Docker Architecture (auto-detected)\nservices:"]
    for svc in services:
        arch_lines.append(f"  {svc['name']}:")
        arch_lines.append(f"    container_name: {svc['container_name']}")
        arch_lines.append(f"    status: {svc['status']}")
        if svc.get('ports'):
            arch_lines.append(f"    ports:")
            for port, host_port in svc['ports'].items():
                arch_lines.append(f"      - \"{host_port}:{port}\"")
    return "\n".join(arch_lines)


def _build_probe_url(target_service: str) -> str:
    """Build a probe URL for a target service (auto-detect Docker vs local)."""
    from services.docker_manager import discover_services
    is_docker = os.path.exists("/.dockerenv")
    services = discover_services()
    for svc in services:
        if svc["name"] == target_service:
            if is_docker:
                internal_port = list(svc["ports"].keys())[0].split("/")[0] if svc.get("ports") else "8000"
                return f"http://{svc['container_name']}:{internal_port}/health"
            else:
                host_port = list(svc["ports"].values())[0] if svc.get("ports") else "8000"
                return f"http://localhost:{host_port}/health"
    # Fallback: use api-gateway on common port
    return "http://localhost:8000/health"


@router.post("/scenario")
def generate_scenario():
    """
    Use Gemini AI to analyze the target application's Docker Compose
    architecture and suggest a chaos engineering test scenario.
    """
    from scenario_generator import generate_chaos_scenario
    architecture = _get_architecture()
    try:
        report = generate_chaos_scenario(architecture)
        return {"scenario": report}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Scenario generation failed. Check if GEMINI_API_KEY is configured. Error: {str(e)}"
        )


# ═══════════════════════════════════════════════════════════
#  NEW AI-POWERED ENDPOINTS
# ═══════════════════════════════════════════════════════════


@router.post("/autopilot")
async def run_autopilot():
    """
    AI Auto-Pilot: Generate a structured test plan via Gemini,
    automatically execute each test, and produce a combined AI report.

    This is the flagship AI feature — one button does everything.
    """
    from ai_autopilot import generate_test_plan, generate_combined_report

    architecture = _get_architecture()

    # Phase 1: Generate structured test plan
    try:
        plan = generate_test_plan(architecture)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"AI test plan generation failed: {str(e)}"
        )

    # Phase 2: Execute each test automatically
    all_results = []
    for i, test in enumerate(plan):
        target = test["target_service"]
        fault = test["fault_type"]
        probe_url = _build_probe_url(target)

        try:
            if fault == "latency":
                result = await run_latency_test(
                    target_service=target,
                    probe_url=probe_url,
                    delay_ms=test.get("delay_ms", 2000),
                    num_requests=3,
                )
            elif fault == "stress":
                result = await run_stress_test(
                    target_service=target,
                    probe_url=probe_url,
                    cpu=test.get("cpu", 2),
                    stress_timeout=test.get("stress_timeout", 20),
                    num_requests=3,
                )
            else:
                result = {"error": f"Unsupported fault type: {fault}"}

            result["test_type"] = fault
            result["source"] = "autopilot"
            result["hypothesis"] = test.get("hypothesis", "")
            result["severity"] = test.get("severity", "unknown")
            _save_entry(result)
            all_results.append(result)
        except Exception as e:
            all_results.append({
                "test_index": i,
                "target_service": target,
                "fault_type": fault,
                "error": str(e),
            })

    # Phase 3: Generate combined AI report
    try:
        combined_report = generate_combined_report(plan, all_results)
    except Exception as e:
        combined_report = f"# Report Generation Failed\n\nError: {str(e)}\n\nRaw results are still available below."

    return {
        "plan": plan,
        "results": all_results,
        "report": combined_report,
    }


@router.post("/compare")
def compare_experiments():
    """
    Cross-run trend analysis: load all experiment history and ask Gemini
    to identify trends, regressions, and improvements.
    """
    from ai_comparator import compare_experiments as _compare

    history = _load_history()
    if len(history) < 2:
        raise HTTPException(
            status_code=400,
            detail=f"Need at least 2 experiments for comparison. Currently have {len(history)}. Run more experiments first.",
        )

    try:
        report = _compare(history)
        return {"report": report, "experiment_count": len(history)}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Comparative analysis failed: {str(e)}"
        )


@router.get("/predict")
async def predict_resilience():
    """
    Pre-experiment resilience prediction: analyze the architecture
    and live health to predict weaknesses BEFORE any faults are injected.
    """
    from ai_predictor import predict_resilience as _predict
    from services.docker_manager import discover_services
    from services.health_checker import check_health

    architecture = _get_architecture()

    # Gather live health status
    services = discover_services()
    live_status = []
    for svc in services:
        host_port = None
        for cp, mp in svc["ports"].items():
            if mp:
                host_port = int(mp)
                break
        status_info = {
            "service": svc["name"],
            "container_name": svc["container_name"],
            "status": svc["status"],
            "ports": svc["ports"],
        }
        if host_port and svc["status"] == "running":
            try:
                health = await check_health("localhost", host_port)
                status_info.update(health)
            except Exception:
                status_info["health"] = "unknown"
        live_status.append(status_info)

    try:
        report = _predict(architecture, live_status)
        return {"report": report}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Predictive analysis failed: {str(e)}"
        )


class AdviseRequest(BaseModel):
    """Schema for real-time AI advisory during active faults."""
    target_service: str
    fault_type: str
    params: Optional[dict] = {}


@router.post("/advise")
async def advise_live(req: AdviseRequest):
    """
    Real-time AI advisory during an active fault injection.
    Provides blast radius assessment, cascading failure prediction,
    and recommended actions.
    """
    from ai_live_advisor import advise_live as _advise
    from services.docker_manager import discover_services
    from services.health_checker import check_health

    active_fault = {
        "service": req.target_service,
        "fault_type": req.fault_type,
        "params": req.params,
    }

    # Gather current live status
    services = discover_services()
    live_status = []
    for svc in services:
        host_port = None
        for cp, mp in svc["ports"].items():
            if mp:
                host_port = int(mp)
                break
        status_info = {
            "service": svc["name"],
            "container_name": svc["container_name"],
            "status": svc["status"],
        }
        if host_port and svc["status"] == "running":
            try:
                health = await check_health("localhost", host_port)
                status_info.update(health)
            except Exception:
                status_info["health"] = "unknown"
        live_status.append(status_info)

    architecture = _get_architecture()

    try:
        report = _advise(active_fault, live_status, architecture)
        return {"report": report}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"AI advisory failed: {str(e)}"
        )


@router.post("/summarize")
def summarize_history():
    """
    AI Executive Summary: Analyze all experiment history and produce
    a concise, stakeholder-ready health verdict.
    """
    from ai_analyst import analyze_results

    history = _load_history()
    if not history:
        raise HTTPException(
            status_code=404,
            detail="No experiment history to summarize.",
        )

    # Build a comprehensive summary prompt via the analyze_results function
    summary_data = {
        "total_experiments": len(history),
        "experiments": history,
        "request_type": "executive_summary",
    }

    try:
        report = analyze_results(summary_data)
        return {"report": report, "experiment_count": len(history)}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Summary generation failed: {str(e)}"
        )
