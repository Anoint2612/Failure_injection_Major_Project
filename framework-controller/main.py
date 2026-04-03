from fastapi import FastAPI, HTTPException
import docker

app = FastAPI()
client = docker.from_env()

@app.get("/")
def root():
    return {"message": "Chaos Controller is Active"}

@app.post("/inject/crash/{service_name}")
def inject_crash(service_name: str):
    """Simulates a hard crash by stopping a container."""
    try:
        # Find the container by name (Docker Compose adds prefixes)
        container = client.containers.get(f"target-app-{service_name}-1")
        container.stop()
        return {"status": "success", "action": f"Stopped {service_name}"}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.post("/recover/{service_name}")
def recover_service(service_name: str):
    """Restores a crashed container."""
    try:
        container = client.containers.get(f"target-app-{service_name}-1")
        container.start()
        return {"status": "success", "action": f"Restarted {service_name}"}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.post("/inject/latency/{service_name}")
def inject_latency(service_name: str, delay_ms: int = 2000):
    """Adds artificial network latency to a service."""
    try:
        container = client.containers.get(f"target-app-{service_name}-1")
        # This command tells Linux to add a 'delay' to the network interface
        cmd = f"tc qdisc add dev eth0 root netem delay {delay_ms}ms"
        container.exec_run(cmd)
        return {"status": "success", "action": f"Added {delay_ms}ms delay to {service_name}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/recover/latency/{service_name}")
def recover_latency(service_name: str):
    """Removes the network latency."""
    try:
        container = client.containers.get(f"target-app-{service_name}-1")
        cmd = "tc qdisc del dev eth0 root netem"
        container.exec_run(cmd)
        return {"status": "success", "action": f"Removed latency from {service_name}"}
    except Exception as e:
        return {"status": "already_clean", "detail": "No latency rules found to remove"}