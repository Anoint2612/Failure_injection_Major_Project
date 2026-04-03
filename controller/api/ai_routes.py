import logging
import os
from fastapi import APIRouter
from core.ai_analyzer import AIAnalyzer

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] [controller/%(module)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S"
)
logger = logging.getLogger(__name__)

router = APIRouter()
ai_analyzer = AIAnalyzer()


@router.get("/ai/scenarios")
def get_suggested_scenarios():
    logger.info("Generating AI chaos scenarios")
    scenarios = ai_analyzer.generate_chaos_scenarios()
    logger.info(f"Returning {len(scenarios) if isinstance(scenarios, list) else 1} scenario(s)")
    return {"suggestions": scenarios}


@router.post("/ai/autopilot/run")
def autopilot_run():
    """
    Called by the dashboard when Autopilot is enabled.
    Generates AI scenarios and queues the first one automatically.
    """
    from api.routes import experiments_queue, experiments_history
    import uuid
    from datetime import datetime, timezone

    logger.info("Autopilot triggered — generating and queueing AI scenario")
    scenarios = ai_analyzer.generate_chaos_scenarios()

    if not isinstance(scenarios, list) or len(scenarios) == 0:
        logger.warning("Autopilot: no scenarios returned from AI analyzer")
        return {"status": "no_scenarios", "queued": None}

    first = scenarios[0]
    experiment_id = f"autopilot-{uuid.uuid4().hex[:8]}"
    entry = {
        "id": experiment_id,
        "name": first.get("name", "autopilot-scenario"),
        "target_selector": first.get("target_selector", {}),
        "parameters": first.get("parameters", {}),
        "auto_abort_threshold_ms": 1000,
        "status": "queued",
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "dispatched_to": None,
        "result": None,
        "source": "autopilot",
        "reasoning": first.get("reasoning", ""),
    }
    experiments_queue.append(entry)
    experiments_history.append(entry)

    logger.info(f"Autopilot queued: '{entry['name']}' (id={experiment_id}) — reason: {entry['reasoning']}")
    return {"status": "queued", "experiment_id": experiment_id, "queued": entry}


@router.get("/ai/report/{experiment_name}")
def get_sre_report(experiment_name: str):
    logger.info(f"Generating SRE report for experiment: {experiment_name}")
    return ai_analyzer.generate_sre_report(experiment_name)
