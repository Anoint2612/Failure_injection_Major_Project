"""
test_executor.py — ChaosController REST API Client

Calls the ChaosController's /experiment/run endpoint for each test
in the configuration and returns the raw telemetry results.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import httpx

from chaos_runner.config_loader import ChaosConfig, TestConfig


@dataclass
class TestResult:
    test_id: str
    test_type: str
    target: str
    raw: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    duration_s: float = 0.0
    success: bool = False


async def _run_single(
    client: httpx.AsyncClient,
    controller_url: str,
    test: TestConfig,
    config: ChaosConfig,
) -> TestResult:
    """Call POST /experiment/run for one test config and return TestResult."""
    svc = config.service_for(test.target)
    params = test.params

    payload: Dict[str, Any] = {
        "target_service": test.target,
        "probe_url": svc.probe_url,
        "fault_type": test.type,
        # Latency params
        "delay_ms": params.delay_ms,
        # Stress params
        "cpu": params.cpu,
        "stress_timeout": params.stress_timeout,
        "num_requests": params.num_requests,
        # Payload params (only used when type == payload)
        "max_operations": params.max_operations,
        "max_cases_per_operation": params.max_cases_per_operation,
    }

    if svc.bearer_token:
        payload["bearer_token"] = svc.bearer_token

    t0 = time.time()
    try:
        resp = await client.post(
            f"{controller_url}/experiment/run",
            json=payload,
            timeout=config.controller.timeout_seconds,
        )
        resp.raise_for_status()
        duration = round(time.time() - t0, 2)
        return TestResult(
            test_id=test.id,
            test_type=test.type,
            target=test.target,
            raw=resp.json(),
            duration_s=duration,
            success=True,
        )
    except httpx.HTTPStatusError as e:
        return TestResult(
            test_id=test.id,
            test_type=test.type,
            target=test.target,
            error=f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            duration_s=round(time.time() - t0, 2),
        )
    except Exception as e:
        return TestResult(
            test_id=test.id,
            test_type=test.type,
            target=test.target,
            error=str(e),
            duration_s=round(time.time() - t0, 2),
        )


async def execute_all(config: ChaosConfig) -> list[TestResult]:
    """
    Execute all tests sequentially (not in parallel) to avoid simultaneous
    fault injection on the same service, which would produce unreliable results.
    """
    results: list[TestResult] = []
    controller_url = config.controller.url.rstrip("/")

    # First, verify the controller is reachable
    async with httpx.AsyncClient(timeout=10) as probe:
        try:
            r = await probe.get(f"{controller_url}/status")
            r.raise_for_status()
        except Exception as e:
            raise ConnectionError(
                f"Cannot reach ChaosController at {controller_url}: {e}\n"
                "Ensure the controller is running before executing tests."
            )

    async with httpx.AsyncClient() as client:
        for test in config.tests:
            result = await _run_single(client, controller_url, test, config)
            results.append(result)

    return results


def run_all(config: ChaosConfig) -> list[TestResult]:
    """Synchronous wrapper for use from the CLI."""
    return asyncio.run(execute_all(config))
