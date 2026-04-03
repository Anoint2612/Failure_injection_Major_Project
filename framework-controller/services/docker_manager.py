"""
Docker Manager — dynamically discovers and manages containers.

Uses Docker Compose labels (com.docker.compose.project / .service)
so it works with ANY target application, not just a specific one.
"""

import docker

_client = docker.from_env()


def get_docker_client():
    """Return the shared Docker client instance."""
    return _client


def discover_services(project: str = None):
    """
    Discover all Docker Compose services currently running.

    Uses container labels set automatically by Docker Compose:
      - com.docker.compose.project  → project name (folder name by default)
      - com.docker.compose.service  → service name from docker-compose.yml

    Args:
        project: Optional project name filter. If None, returns all compose services.

    Returns:
        List of dicts with service metadata including dynamic port mappings.
    """
    containers = _client.containers.list(all=True)
    services = []

    for container in containers:
        labels = container.labels
        compose_project = labels.get("com.docker.compose.project", "")
        compose_service = labels.get("com.docker.compose.service", "")

        # Skip non-compose containers (e.g. standalone docker run)
        if not compose_service:
            continue

        # If a project filter is given, only include matching containers
        if project and compose_project != project:
            continue

        # Dynamically extract host port mappings from container inspection
        ports = {}
        port_bindings = container.attrs.get("NetworkSettings", {}).get("Ports", {}) or {}
        for container_port, host_bindings in port_bindings.items():
            if host_bindings:
                ports[container_port] = host_bindings[0].get("HostPort")

        services.append({
            "name": compose_service,
            "container_name": container.name,
            "project": compose_project,
            "status": container.status,  # "running", "exited", "paused", etc.
            "ports": ports,
        })

    return services


def get_container(service_name: str, project: str = None):
    """
    Find a running container by its Docker Compose service name.

    Searches using the `com.docker.compose.service` label so it works
    regardless of container naming conventions (prefixes, suffixes, etc.).

    Raises ValueError if no matching container is found.
    """
    filters = {"label": f"com.docker.compose.service={service_name}"}
    containers = _client.containers.list(all=True, filters=filters)

    if project:
        containers = [
            c for c in containers
            if c.labels.get("com.docker.compose.project") == project
        ]

    if not containers:
        raise ValueError(f"No container found for service '{service_name}'")

    return containers[0]


def get_host_port(service_name: str, project: str = None):
    """
    Get the first mapped host port for a service.

    Useful for dynamically constructing health-check or probe URLs.
    Returns None if no port is mapped.
    """
    container = get_container(service_name, project)
    port_bindings = container.attrs.get("NetworkSettings", {}).get("Ports", {}) or {}

    for container_port, host_bindings in port_bindings.items():
        if host_bindings:
            return int(host_bindings[0].get("HostPort"))

    return None
