"""
Experiment Runner — parameterized chaos experiments.

All parameters (target service, probe URL, fault params) are passed in
so this module has zero knowledge of the target application.

IMPORTANT: On Docker Desktop (Mac/Windows), tc netem rules only affect
INTER-CONTAINER traffic on the Docker bridge network, NOT host-to-container
traffic via port mapping. Therefore:
  - Inject the fault on a DOWNSTREAM service (e.g., auth-service)
  - Probe through an UPSTREAM endpoint that calls the downstream service
    (e.g., http://localhost:8000/dashboard which calls auth-service)
"""

import httpx
import time
import asyncio

from services.docker_manager import get_container
from config import settings


async def _measure_probe(client: httpx.AsyncClient, probe_url: str, num_requests: int, delay_between: float = 0):
    """Send probe requests and return latency measurements."""
    results = []
    for i in range(1, num_requests + 1):
        start = time.time()
        try:
            resp = await client.get(probe_url)
            latency = round(time.time() - start, 3)
            results.append({
                "request": i,
                "latency": latency,
                "status": resp.status_code,
            })
        except Exception:
            results.append({
                "request": i,
                "latency": round(settings.EXPERIMENT_TIMEOUT, 3),
                "status": "timeout",
            })
        if delay_between > 0:
            await asyncio.sleep(delay_between)
    return results


async def run_latency_test(
    target_service: str,
    probe_url: str,
    delay_ms: int = 3000,
    num_requests: int = 5,
    project: str = None,
):
    """
    Inject network latency and measure impact.

    Workflow:
      1. Measure baseline (before fault)
      2. Inject latency via tc netem
      3. Measure during fault
      4. Auto-recover
      5. Measure after recovery

    Returns baseline, during-fault, and post-recovery measurements.
    """
    container = get_container(target_service, project)

    async with httpx.AsyncClient(timeout=settings.EXPERIMENT_TIMEOUT) as client:
        # 1. Baseline measurement
        baseline = await _measure_probe(client, probe_url, num_requests)

        # 2. Inject latency
        container.exec_run("tc qdisc del dev eth0 root")
        container.exec_run(f"tc qdisc add dev eth0 root netem delay {delay_ms}ms")

        # Small wait for rules to take effect
        await asyncio.sleep(0.5)

        # 3. Measure under fault
        try:
            during_fault = await _measure_probe(client, probe_url, num_requests)
        finally:
            # 4. Always recover
            container.exec_run("tc qdisc del dev eth0 root")

        # Small wait for recovery
        await asyncio.sleep(0.5)

        # 5. Post-recovery measurement
        post_recovery = await _measure_probe(client, probe_url, num_requests)

    return {
        "baseline": baseline,
        "during_fault": during_fault,
        "post_recovery": post_recovery,
        "config": {
            "target_service": target_service,
            "probe_url": probe_url,
            "delay_ms": int(delay_ms),
            "num_requests": num_requests,
        },
    }


async def run_stress_test(
    target_service: str,
    probe_url: str,
    cpu: int = 2,
    stress_timeout: int = 20,
    num_requests: int = 3,
    project: str = None,
):
    """
    Inject CPU stress and measure impact.

    Same 3-phase workflow: baseline → during fault → post recovery.
    """
    container = get_container(target_service, project)

    async with httpx.AsyncClient(timeout=settings.EXPERIMENT_TIMEOUT) as client:
        # 1. Baseline
        baseline = await _measure_probe(client, probe_url, num_requests, delay_between=0.5)

        # 2. Inject stress
        container.exec_run(
            f"stress-ng --cpu {cpu} --timeout {stress_timeout}s",
            detach=True,
        )
        await asyncio.sleep(2)  # Let stress ramp up

        # 3. Measure under fault
        try:
            during_fault = await _measure_probe(client, probe_url, num_requests, delay_between=1)
        finally:
            container.exec_run("pkill stress-ng")

        await asyncio.sleep(1)

        # 4. Post-recovery
        post_recovery = await _measure_probe(client, probe_url, num_requests, delay_between=0.5)

    return {
        "baseline": baseline,
        "during_fault": during_fault,
        "post_recovery": post_recovery,
        "config": {
            "target_service": target_service,
            "probe_url": probe_url,
            "cpu": int(cpu),
            "stress_timeout": int(stress_timeout),
            "num_requests": num_requests,
        },
    }
