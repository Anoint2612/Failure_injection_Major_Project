"""
Recovery Router — generic fault recovery via the fault registry.

Mirrors the injection router: a single endpoint dispatches to the
fault's recover() method.
"""

import json
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from services.docker_manager import get_container
from services.fault_library import get_fault

router = APIRouter(prefix="/recover", tags=["Recovery"])

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
def recover_fault(fault_type: str, service_name: str, project: str = None):
    """
    Recover from any registered fault on a service container.

    Path params:
        fault_type: Name from the fault registry (e.g., 'crash', 'latency', 'packet_loss')
        service_name: Docker Compose service name
    """
    try:
        fault = get_fault(fault_type)
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        container = get_container(service_name, project)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    try:
        result = fault.recover(container)

        # Log to experiment_results.json
        _append_event({
            "source": "manual_recover",
            "fault_type": fault_type,
            "service": service_name,
            "result": result,
        })

        return {"status": "success", **result}
    except Exception as e:
        return {"status": "info", "detail": f"Recovery note: {str(e)}"}
