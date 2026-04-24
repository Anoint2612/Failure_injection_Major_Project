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

from services.experiment_runner import run_latency_test, run_stress_test

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
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown fault type: '{req.fault_type}'. Use 'latency' or 'stress'.",
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


@router.post("/scenario")
def generate_scenario():
    """
    Use Gemini AI to analyze the target application's Docker Compose
    architecture and suggest a chaos engineering test scenario.
    """
    from scenario_generator import generate_chaos_scenario
    
    # Try multiple paths for docker-compose.yml (works both locally and in Docker)
    compose_paths = [
        "../target-app/docker-compose.yml",
        "/app/../target-app/docker-compose.yml",
    ]
    
    architecture = None
    for path in compose_paths:
        if os.path.exists(path):
            with open(path, "r") as f:
                architecture = f.read()
            break
    
    if not architecture:
        # If no compose file found, build architecture from live Docker state
        from services.docker_manager import list_services
        services = list_services()
        arch_lines = ["# Live Docker Architecture (auto-detected)\nservices:"]
        for svc in services:
            arch_lines.append(f"  {svc['name']}:")
            arch_lines.append(f"    container_name: {svc['container_name']}")
            arch_lines.append(f"    status: {svc['status']}")
            if svc.get('ports'):
                arch_lines.append(f"    ports:")
                for port, host_port in svc['ports'].items():
                    arch_lines.append(f"      - \"{host_port}:{port}\"")
        architecture = "\n".join(arch_lines)
    
    try:
        report = generate_chaos_scenario(architecture)
        return {"scenario": report}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Scenario generation failed. Check if GEMINI_API_KEY is configured. Error: {str(e)}"
        )
