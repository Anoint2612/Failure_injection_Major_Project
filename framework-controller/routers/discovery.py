"""
Discovery Router — dynamic service discovery, live health status, and fault catalog.

Everything here is discovered at runtime via Docker and the fault registry.
No hardcoded service names, ports, URLs, or fault types.
"""

import time
from fastapi import APIRouter
from services.docker_manager import discover_services
from services.health_checker import check_health
from services.fault_library import list_faults

router = APIRouter(tags=["Discovery"])


@router.get("/services")
def get_services(project: str = None):
    """Dynamically discover all Docker Compose services."""
    services = discover_services(project=project)
    return {"services": services}


@router.get("/status")
async def get_status(project: str = None):
    """
    Live health check for all discovered services.

    Extracts mapped host ports from Docker inspection and probes each
    service's health endpoint. Returns real-time up/down status.
    """
    services = discover_services(project=project)
    statuses = []

    for svc in services:
        # Find the first mapped host port
        host_port = None
        for container_port, mapped_port in svc["ports"].items():
            if mapped_port:
                host_port = int(mapped_port)
                break

        if host_port and svc["status"] == "running":
            health = await check_health("localhost", host_port)
        else:
            health = {"status": "down", "latency_ms": None, "http_code": None}

        statuses.append({
            "service": svc["name"],
            "container_name": svc["container_name"],
            "container_status": svc["status"],
            "project": svc["project"],
            "ports": svc["ports"],
            **health,
        })

    return {"services": statuses, "timestamp": time.time()}


@router.get("/faults")
def get_faults():
    """
    Return the full catalog of available fault types.

    The frontend uses this to dynamically render injection controls —
    including parameter names, types, defaults, and ranges.
    """
    return {"faults": list_faults()}
