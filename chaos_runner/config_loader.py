"""
config_loader.py — YAML Configuration Schema Loader

Parses and validates chaos-config.yml using Pydantic.
Provides sane defaults and clear validation errors for misconfigured suites.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


# ── Schema ────────────────────────────────────────────────────────────────────

class ControllerConfig(BaseModel):
    url: str = "http://localhost:5050"
    timeout_seconds: int = 300


class Thresholds(BaseModel):
    latency_regression_percent: float = 50.0
    max_5xx_rate_percent: float = 5.0
    max_payload_crash_rate_percent: float = 0.0


class ServiceConfig(BaseModel):
    name: str
    probe_url: str
    openapi_url: Optional[str] = None
    bearer_token: Optional[str] = None
    bearer_token_env: Optional[str] = None  # reads token from env var

    @model_validator(mode="after")
    def resolve_token(self) -> "ServiceConfig":
        if self.bearer_token_env and not self.bearer_token:
            self.bearer_token = os.getenv(self.bearer_token_env)
        return self


class TestParams(BaseModel):
    # Latency params
    delay_ms: int = 3000
    # Stress params
    cpu: int = 2
    stress_timeout: int = 20
    # Common
    num_requests: int = 5
    # Payload params
    max_operations: int = 5
    max_cases_per_operation: int = 10

    class Config:
        extra = "allow"


class TestConfig(BaseModel):
    id: str
    type: str  # latency | stress | payload
    target: str  # must match a service name
    params: TestParams = Field(default_factory=TestParams)
    on_fail: str = "block"  # block | warn

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        allowed = {"latency", "stress", "payload"}
        if v not in allowed:
            raise ValueError(f"type must be one of {allowed}, got '{v}'")
        return v

    @field_validator("on_fail")
    @classmethod
    def validate_on_fail(cls, v: str) -> str:
        allowed = {"block", "warn"}
        if v not in allowed:
            raise ValueError(f"on_fail must be 'block' or 'warn', got '{v}'")
        return v


class ReportConfig(BaseModel):
    output_path: str = "chaos-report.html"
    json_path: str = "chaos-report.json"
    ai_summary: bool = True
    fail_on: str = "block"


class ChaosConfig(BaseModel):
    version: str = "1.0"
    project: str = "unnamed-project"
    controller: ControllerConfig = Field(default_factory=ControllerConfig)
    thresholds: Thresholds = Field(default_factory=Thresholds)
    services: List[ServiceConfig] = Field(default_factory=list)
    tests: List[TestConfig] = Field(default_factory=list)
    report: ReportConfig = Field(default_factory=ReportConfig)

    @model_validator(mode="after")
    def validate_test_targets(self) -> "ChaosConfig":
        service_names = {s.name for s in self.services}
        for test in self.tests:
            if test.target not in service_names:
                raise ValueError(
                    f"Test '{test.id}' references target '{test.target}', "
                    f"but no service with that name exists. "
                    f"Available services: {sorted(service_names)}"
                )
        return self

    def service_for(self, name: str) -> ServiceConfig:
        for svc in self.services:
            if svc.name == name:
                return svc
        raise KeyError(f"Service '{name}' not found in config")


# ── Loader ────────────────────────────────────────────────────────────────────

def load_config(path: str | Path) -> ChaosConfig:
    """Load and validate a chaos-config.yml file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"Config file not found: {p.resolve()}\n"
            "Create one from the example: cp chaos-config.example.yml chaos-config.yml"
        )
    with open(p, "r") as f:
        raw: Dict[str, Any] = yaml.safe_load(f) or {}

    return ChaosConfig.model_validate(raw)
