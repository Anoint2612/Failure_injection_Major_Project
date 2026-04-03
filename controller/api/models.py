from pydantic import BaseModel
from typing import Dict, Optional

class AgentRegistration(BaseModel):
    hostname: str
    ip_address: str
    discovery_profile: Dict

class ExperimentDef(BaseModel):
    name: str
    target_selector: Dict[str, str]
    parameters: Dict[str, str]
    auto_abort_threshold_ms: Optional[int] = 500
    duration_seconds: Optional[int] = 30  # TTL for auto-revert on the agent

class ExperimentResult(BaseModel):
    experiment_id: str
    status: str   # "running" | "completed" | "failed"
    message: str
