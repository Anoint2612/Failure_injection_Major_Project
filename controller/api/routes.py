import uuid
import logging
import os
from fastapi import APIRouter, HTTPException
from typing import Dict
from datetime import datetime, timezone
from api.models import AgentRegistration, ExperimentDef, ExperimentResult
from core.safety_engine import SafetyEngine

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] [controller/%(module)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S"
)
logger = logging.getLogger(__name__)

router = APIRouter()
safety_engine = SafetyEngine()

# In-memory stores (survive controller restarts only if process stays up)
agents_registry: Dict[str, dict] = {}
experiments_queue = []
experiments_history = []  # Full audit log


@router.post("/agents/register")
def register_agent(agent: AgentRegistration):
    agent_id = f"agent-{uuid.uuid4().hex[:8]}"
    agents_registry[agent_id] = {
        "hostname": agent.hostname,
        "ip_address": agent.ip_address,
        "profile": agent.discovery_profile,
        "last_heartbeat": datetime.now(timezone.utc).isoformat(),
        "status": "idle"
    }
    logger.info(f"Agent registered: {agent_id} | host={agent.hostname} | ip={agent.ip_address}")
    return {"status": "registered", "agent_id": agent_id}


@router.get("/agents")
def list_agents():
    return {"agents": agents_registry}


@router.post("/agents/{agent_id}/heartbeat")
def heartbeat(agent_id: str):
    if agent_id not in agents_registry:
        logger.warning(f"Heartbeat from unknown agent: {agent_id}. Requesting re-register.")
        raise HTTPException(status_code=404, detail="Agent not found. Please re-register.")

    agents_registry[agent_id]["last_heartbeat"] = datetime.now(timezone.utc).isoformat()

    # Safety check — abort all if Prometheus signals blast-radius exceeded
    if not safety_engine.check_health():
        logger.warning(f"Safety engine triggered ABORT_ALL for agent {agent_id}")
        return {"action": "ABORT_ALL"}

    # Dispatch next queued experiment to this agent
    if experiments_queue:
        exp = experiments_queue.pop(0)
        exp["dispatched_at"] = datetime.now(timezone.utc).isoformat()
        exp["dispatched_to"] = agent_id

        # Update history entry to dispatched
        for entry in experiments_history:
            if entry["id"] == exp.get("id"):
                entry["status"] = "dispatched"
                entry["dispatched_to"] = agent_id
                break

        agents_registry[agent_id]["status"] = "running_experiment"
        logger.info(f"Dispatching experiment '{exp['name']}' (id={exp.get('id')}) to agent {agent_id}")
        return {"action": "RUN_EXPERIMENT", "payload": exp}

    # No work — mark idle
    if agents_registry[agent_id].get("status") == "running_experiment":
        agents_registry[agent_id]["status"] = "idle"

    logger.debug(f"Heartbeat from {agent_id}: SLEEP")
    return {"action": "SLEEP"}


@router.post("/experiments/trigger")
def trigger_experiment(exp: ExperimentDef):
    experiment_id = f"exp-{uuid.uuid4().hex[:8]}"
    entry = {
        "id": experiment_id,
        "name": exp.name,
        "target_selector": exp.target_selector,
        "parameters": {**exp.parameters, "duration_seconds": str(exp.duration_seconds)},
        "auto_abort_threshold_ms": exp.auto_abort_threshold_ms,
        "status": "queued",
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "dispatched_to": None,
        "result": None,
    }
    experiments_queue.append(entry)
    experiments_history.append(entry)

    logger.info(f"Experiment queued: '{exp.name}' (id={experiment_id}) | target={exp.target_selector}")
    return {"status": "queued", "experiment_id": experiment_id, "experiment": exp.name}


@router.get("/experiments")
def list_experiments():
    return {"experiments": experiments_history[-50:]}  # Last 50 only


@router.post("/agents/{agent_id}/experiment/result")
def report_experiment_result(agent_id: str, result: ExperimentResult):
    if agent_id not in agents_registry:
        raise HTTPException(status_code=404, detail="Agent not found.")

    # Update matching history entry
    updated = False
    for entry in experiments_history:
        if entry["id"] == result.experiment_id:
            entry["status"] = result.status
            entry["result"] = result.message
            entry["completed_at"] = datetime.now(timezone.utc).isoformat()
            updated = True
            break

    if result.status in ("completed", "failed"):
        agents_registry[agent_id]["status"] = "idle"

    level = logging.INFO if result.status == "completed" else logging.WARNING
    logger.log(level, f"Experiment result from {agent_id}: id={result.experiment_id} status={result.status} — {result.message}")

    if not updated:
        logger.warning(f"Result for unknown experiment id={result.experiment_id} from agent {agent_id}")

    return {"acknowledged": True}


@router.get("/score")
def resilience_score():
    """Returns a 0-100 Resilience Score based on experiment history."""
    if not experiments_history:
        return {"score": 100, "detail": "No experiments run yet — baseline score."}

    total = len(experiments_history)
    completed = sum(1 for e in experiments_history if e["status"] == "completed")
    failed = sum(1 for e in experiments_history if e["status"] == "failed")

    # Score: starts at 100, -10 per failed experiment, +2 per completed
    score = max(0, min(100, 100 - (failed * 10) + (completed * 2)))
    return {
        "score": score,
        "total_experiments": total,
        "completed": completed,
        "failed": failed,
        "detail": f"{completed}/{total} experiments completed successfully"
    }
