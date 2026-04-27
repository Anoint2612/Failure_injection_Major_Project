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


async def run_payload_test(
    target_service: str,
    probe_url: str,
    project: str = None,
    bearer_token: str = None,
):
    """
    Combined Payload Suite:
    1. Vulnerability Scan: Tries to discover OpenAPI and fuzz endpoints (incl. SQLi/XSS).
       Falls back to targeted single-endpoint payloads if OpenAPI fails.
    2. Degradation Test: 3-phase latency test while sustained Huge JSON bombing.
    """
    payload_results = []
    
    # Try OpenAPI Fuzzing First
    try:
        from services.openapi_fuzzer import run_payload_resilience_suite
        from services.docker_manager import discover_services
        import os
        
        def _is_docker() -> bool:
            return os.path.exists("/.dockerenv")
            
        def _first_port(ports: dict) -> tuple:
            if not isinstance(ports, dict) or not ports: return None
            k = next(iter(ports.keys()))
            return k, ports.get(k)

        # Discover correct base_url and openapi_url
        services = discover_services(project=project)
        is_docker = _is_docker()
        openapi_url = None
        base_url = None
        
        for svc in services:
            if svc["name"] == target_service:
                p = _first_port(svc.get("ports") or {})
                if p:
                    container_port, mapped_port = p
                    internal_port = container_port.split("/")[0]
                    host = svc["container_name"] if is_docker else "localhost"
                    port = internal_port if is_docker else mapped_port
                    if port:
                        base_url = f"http://{host}:{port}"
                        openapi_url = f"{base_url}/openapi.json"
                break
                
        if not openapi_url:
            raise ValueError("Could not discover OpenAPI port for target service")
        
        suite = await run_payload_resilience_suite(
            openapi_url=openapi_url,
            base_url=base_url,
            bearer_token=bearer_token,
            modes=["payload"], # Focus on JSON body mutations
            max_operations=5,
            max_cases_per_operation=10,
            concurrency=5,
            request_timeout_s=5.0
        )
        
        for r in suite.get("results", []):
            payload_results.append({
                "payload_name": r.get("kind"),
                "description": f"{r.get('method')} {r.get('path')}",
                "latency": r.get("latency"),
                "status": r.get("status"),
                "request_body": r.get("request_body")
            })
    except Exception as e:
        print(f"OpenAPI Fuzzing failed or unavailable for {target_service}: {e}")
        # Fallback to hardcoded targeted payloads
        payloads = [
            {"name": "valid_json", "description": "Standard valid JSON payload", "data": '{"test": "valid payload"}', "headers": {"Content-Type": "application/json"}},
            {"name": "malformed_json", "description": "JSON with missing closing bracket", "data": '{"test": "broken payload"', "headers": {"Content-Type": "application/json"}},
            {"name": "huge_json", "description": "Valid JSON but very large (512KB)", "data": '{"data": "' + ('x' * 512 * 1024) + '"}', "headers": {"Content-Type": "application/json"}},
            {"name": "sql_injection", "description": "Common SQL injection pattern", "data": '{"username": "admin\' OR 1=1--"}', "headers": {"Content-Type": "application/json"}},
            {"name": "xss", "description": "Cross-site scripting vector", "data": '{"comment": "<script>alert(1)</script>"}', "headers": {"Content-Type": "application/json"}}
        ]
        async with httpx.AsyncClient(timeout=settings.EXPERIMENT_TIMEOUT) as client:
            for p in payloads:
                start = time.time()
                try:
                    resp = await client.post(probe_url, content=p["data"], headers=p["headers"])
                    latency = round((time.time() - start) * 1000, 1) # ms
                    payload_results.append({
                        "payload_name": p["name"],
                        "description": p["description"],
                        "latency": latency,
                        "status": resp.status_code,
                        "request_body": p["data"]
                    })
                except Exception as e:
                    latency = round((time.time() - start) * 1000, 1)
                    payload_results.append({
                        "payload_name": p["name"],
                        "description": p["description"],
                        "latency": latency,
                        "status": "timeout_or_error",
                        "request_body": p["data"]
                    })
                await asyncio.sleep(0.5)

    # --- PART 2: 3-Phase Bombing Load Test ---
    huge_data = '{"data": "' + ('x' * 512 * 1024) + '"}'
    huge_headers = {"Content-Type": "application/json"}
    
    async with httpx.AsyncClient(timeout=settings.EXPERIMENT_TIMEOUT) as client:
        # 1. Baseline
        baseline = await _measure_probe(client, probe_url, num_requests=3, delay_between=0.5)

        # 2. Inject Fault (Spam huge JSON in the background)
        bombing_active = True
        
        async def spam_payload():
            while bombing_active:
                try:
                    await client.post(probe_url, content=huge_data, headers=huge_headers)
                except Exception:
                    pass
                await asyncio.sleep(0.01)

        bomb_task = asyncio.create_task(spam_payload())
        await asyncio.sleep(1) # Let the bomb spool up

        # 3. Measure during fault
        try:
            during_fault = await _measure_probe(client, probe_url, num_requests=3, delay_between=1.0)
        finally:
            bombing_active = False # Stop the bomber
            await bomb_task
            
        await asyncio.sleep(1) # Let system recover

        # 4. Post-recovery
        post_recovery = await _measure_probe(client, probe_url, num_requests=3, delay_between=0.5)

    return {
        "payload_results": payload_results,
        "baseline": baseline,
        "during_fault": during_fault,
        "post_recovery": post_recovery,
        "config": {
            "target_service": target_service,
            "probe_url": probe_url,
            "test_type": "payload_suite"
        }
    }
