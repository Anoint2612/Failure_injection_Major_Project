"""
Health Checker — async service health probing.

Works with any HTTP service that exposes a health endpoint.
The health path is configurable via the HEALTH_PATH env var.
"""

import httpx
import time

from config import settings


async def check_health(host: str, port: int, path: str = None, timeout: float = None):
    """
    Probe a single service's health endpoint and measure response time.

    Args:
        host: Hostname (typically 'localhost' for port-mapped containers).
        port: Host-mapped port number.
        path: Health endpoint path (defaults to settings.HEALTH_PATH).
        timeout: Request timeout in seconds (defaults to settings.HEALTH_TIMEOUT).

    Returns:
        Dict with 'status' ('up'/'down'), 'latency_ms', and 'http_code'.
    """
    path = path or settings.HEALTH_PATH
    timeout = timeout or settings.HEALTH_TIMEOUT
    url = f"http://{host}:{port}{path}"

    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            latency_ms = round((time.time() - start) * 1000, 1)
            return {
                "status": "up",
                "latency_ms": latency_ms,
                "http_code": resp.status_code,
            }
    except Exception:
        return {
            "status": "down",
            "latency_ms": None,
            "http_code": None,
        }
