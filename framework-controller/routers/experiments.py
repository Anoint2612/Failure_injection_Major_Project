"""
Experiments Router — parameterized chaos experiments.

The frontend provides all parameters (target service, probe URL, fault type)
so the controller never makes assumptions about the target application.
"""

import json
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from services.experiment_runner import run_latency_test, run_stress_test

router = APIRouter(prefix="/experiment", tags=["Experiments"])

RESULTS_FILE = "experiment_results.json"


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

    # Persist results for later retrieval / AI analysis
    with open(RESULTS_FILE, "w") as f:
        json.dump(results, f, indent=4)

    return results


@router.get("/results")
def get_results():
    """Return the most recently saved experiment results."""
    if not os.path.exists(RESULTS_FILE):
        raise HTTPException(
            status_code=404,
            detail="No experiment results found. Run an experiment first.",
        )
    with open(RESULTS_FILE, "r") as f:
        return json.load(f)
