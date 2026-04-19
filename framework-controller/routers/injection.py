"""
Injection Router — generic fault injection via the fault registry.

A single endpoint handles ALL fault types by dispatching to the fault library.
Adding a new fault type requires zero changes to this router.
"""

import json
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from services.docker_manager import get_container
from services.fault_library import get_fault

router = APIRouter(prefix="/inject", tags=["Injection"])

RESULTS_FILE = "experiment_results.json"


def _append_event(entry: dict):
    """Append a timestamped event to experiment_results.json."""
    history = []
    if os.path.exists(RESULTS_FILE):
        try:
            with open(RESULTS_FILE, "r") as f:
                data = json.load(f)
                history = data if isinstance(data, list) else [data]
        except (json.JSONDecodeError, IOError):
            pass
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    history.append(entry)
    with open(RESULTS_FILE, "w") as f:
        json.dump(history, f, indent=4)


@router.post("/{fault_type}/{service_name}")
def inject_fault(fault_type: str, service_name: str, request: Request, project: str = None):
    """
    Inject any registered fault into a service container.

    Path params:
        fault_type:   Name from the fault registry (e.g., 'crash', 'latency', 'packet_loss')
        service_name: Docker Compose service name

    Query params:
        All fault-specific parameters (e.g., delay_ms=3000, percent=30)
        project: Optional Docker Compose project filter
    """
    try:
        fault = get_fault(fault_type)
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        container = get_container(service_name, project)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Forward all query parameters to the fault's inject() method
    params = dict(request.query_params)
    params.pop("project", None)  # Already consumed above

    try:
        result = fault.inject(container, **params)

        # Log to experiment_results.json
        _append_event({
            "source": "manual_inject",
            "fault_type": fault_type,
            "service": service_name,
            "parameters": params,
            "result": result,
        })

        return {"status": "success", **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
