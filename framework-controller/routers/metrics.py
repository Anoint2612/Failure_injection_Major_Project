"""
Metrics Router — Prometheus query proxy.

Relays PromQL queries to a Prometheus instance so the frontend
doesn't need direct access (avoids CORS issues).
The Prometheus URL is configurable via the PROMETHEUS_URL env var.
"""

import httpx
from fastapi import APIRouter, HTTPException
from config import settings

router = APIRouter(prefix="/prometheus", tags=["Metrics"])


@router.get("/query")
async def prometheus_proxy(q: str):
    """
    Proxy a PromQL query to Prometheus.

    Usage: GET /prometheus/query?q=up
    """
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            resp = await client.get(
                f"{settings.PROMETHEUS_URL}/api/v1/query",
                params={"query": q},
            )
            return resp.json()
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail=f"Prometheus unreachable: {str(e)}",
            )
