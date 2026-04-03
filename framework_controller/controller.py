import subprocess
from typing import List, Optional
from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from typing import List
import os
import json
import datetime
import requests

# MongoDB setup
from pymongo import MongoClient
from bson import json_util

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
mongo_client = None
db = None
experiments_collection = None
metrics_collection = None

try:
    mongo_client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=2000)
    mongo_client.admin.command('ping')
    db = mongo_client["failure_injection"]
    experiments_collection = db["experiments"]
    metrics_collection = db["metrics"]
    print("MongoDB connected successfully")
except Exception as e:
    print(f"MongoDB not available: {e}. Continuing without MongoDB.")

app = FastAPI(title="Failure Injection Controller")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class InjectRequest(BaseModel):
    services: List[str]


# Mapping from logical service name to Docker container name
_service_to_container = {
    "gateway": "fi_gateway",
    "auth": "fi_auth",
    "data": "fi_data",
}


def _container_name(service: str) -> str:
    return _service_to_container.get(service, service)


class CompoundInjectRequest(BaseModel):
    latency_ms: Optional[int] = None
    latency_target: Optional[str] = None
    cpu_exhaustion_percent: Optional[int] = None
    cpu_target: Optional[str] = None


@app.post("/inject/stop")
def stop_services(req: InjectRequest):
    """Stop listed services using docker-compose (simple fault injection)."""
    results = {}
    for svc in req.services:
        cmd = ["docker-compose", "stop", svc]
        res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        results[svc] = {
            "rc": res.returncode,
            "stdout": res.stdout,
            "stderr": res.stderr,
        }
    return results


@app.post("/rollback/start")
def start_services(req: InjectRequest):
    """Start listed services to rollback fault injection."""
    results = {}
    for svc in req.services:
        cmd = ["docker-compose", "start", svc]
        res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        results[svc] = {
            "rc": res.returncode,
            "stdout": res.stdout,
            "stderr": res.stderr,
        }
    return results


@app.get("/status")
def status():
    """Return a quick docker-compose ps summary."""
    cmd = ["docker-compose", "ps"]
    res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return {"rc": res.returncode, "out": res.stdout}


# Endpoint to list markdown reports
@app.get("/reports")
def list_reports():
    reports_dir = os.path.join(ROOT, "reports")
    if not os.path.isdir(reports_dir):
        return {"reports": []}
    files = [f for f in os.listdir(reports_dir) if f.endswith(".md")]
    return {"reports": files}


# Endpoint to retrieve a specific report's markdown content
@app.get("/reports/{filename}")
def get_report(filename: str):
    reports_dir = os.path.join(ROOT, "reports")
    safe_path = os.path.abspath(os.path.join(reports_dir, filename))
    if not safe_path.startswith(os.path.abspath(reports_dir)):
        return {"error": "Invalid filename"}
    if not os.path.isfile(safe_path):
        return {"error": "File not found"}
    with open(safe_path, "r", encoding="utf-8") as fp:
        return {"content": fp.read()}


# Endpoint to inject compound faults
@app.post("/inject/compound")
def inject_compound(req: CompoundInjectRequest):
    """Inject network latency and/or CPU exhaustion as defined in the request."""
    results = {}
    if req.latency_ms and req.latency_target:
        container = _container_name(req.latency_target)
        cmd = [
            "docker",
            "exec",
            container,
            "tc",
            "qdisc",
            "add",
            "dev",
            "eth0",
            "root",
            "netem",
            "delay",
            f"{req.latency_ms}ms",
        ]
        res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        results["latency"] = {
            "rc": res.returncode,
            "stdout": res.stdout,
            "stderr": res.stderr,
        }
    if req.cpu_exhaustion_percent and req.cpu_target:
        container = _container_name(req.cpu_target)
        fraction = req.cpu_exhaustion_percent / 100.0
        cmd = ["docker", "update", container, "--cpus", str(fraction)]
        res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        results["cpu"] = {
            "rc": res.returncode,
            "stdout": res.stdout,
            "stderr": res.stderr,
        }
    return results


# Endpoint to rollback compound faults
@app.post("/rollback/compound")
def rollback_compound(req: CompoundInjectRequest):
    """Remove latency and reset CPU limits."""
    results = {}
    if req.latency_target:
        container = _container_name(req.latency_target)
        cmd = [
            "docker",
            "exec",
            container,
            "tc",
            "qdisc",
            "del",
            "dev",
            "eth0",
            "root",
            "netem",
        ]
        res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        results["latency"] = {
            "rc": res.returncode,
            "stdout": res.stdout,
            "stderr": res.stderr,
        }
    if req.cpu_target:
        container = _container_name(req.cpu_target)
        # Reset CPU limit to full (2 CPUs assumed)
        cmd = ["docker", "update", container, "--cpus", "2"]
        res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        results["cpu"] = {
            "rc": res.returncode,
            "stdout": res.stdout,
            "stderr": res.stderr,
        }
    return results


# Endpoint to trigger the autonomous runner
@app.post("/run_ai_experiment")
def run_ai_experiment():
    cmd = ["python3", os.path.join(ROOT, "autonomous_runner.py")]
    res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return {"rc": res.returncode, "stdout": res.stdout, "stderr": res.stderr}


# ========== MongoDB Endpoints ==========


@app.post("/experiments/save")
def save_experiment(data: dict):
    """Save experiment result to MongoDB"""
    if experiments_collection is None:
        return {"error": "MongoDB not connected"}
    data["timestamp"] = datetime.datetime.utcnow()
    result = experiments_collection.insert_one(data)
    return {"id": str(result.inserted_id), "status": "saved"}


@app.get("/experiments/history")
def get_experiment_history(limit: int = 10):
    """Get experiment history from MongoDB"""
    if experiments_collection is None:
        return {"error": "MongoDB not connected", "experiments": []}
    experiments = list(experiments_collection.find().sort("timestamp", -1).limit(limit))
    # Convert ObjectId to string for JSON serialization
    for exp in experiments:
        exp["_id"] = str(exp["_id"])
        if "timestamp" in exp:
            exp["timestamp"] = exp["timestamp"].isoformat()
    return {"experiments": experiments}


# ========== Real-time Metrics from Prometheus ==========

PROMETHEUS_URL = "http://localhost:9090"


@app.get("/metrics/realtime")
def get_realtime_metrics():
    """Get real-time metrics from Prometheus"""
    metrics = {}

    # Query gateway requests total
    try:
        resp = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": "gateway_requests_total"},
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "success" and data.get("data", {}).get("result"):
                metrics["gateway_requests"] = data["data"]["result"][0]["value"][1]
    except Exception as e:
        metrics["gateway_requests_error"] = str(e)

    # Query auth requests total
    try:
        resp = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": "auth_requests_total"},
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "success" and data.get("data", {}).get("result"):
                metrics["auth_requests"] = data["data"]["result"][0]["value"][1]
    except Exception as e:
        metrics["auth_requests_error"] = str(e)

    # Query data requests total
    try:
        resp = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": "data_requests_total"},
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "success" and data.get("data", {}).get("result"):
                metrics["data_requests"] = data["data"]["result"][0]["value"][1]
    except Exception as e:
        metrics["data_requests_error"] = str(e)

    return metrics


@app.get("/metrics/latency")
def get_latency_metrics():
    """Get latency time series from Prometheus"""
    try:
        resp = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query_range",
            params={
                "query": "rate(gateway_requests_total[1m])",
                "start": int(datetime.datetime.utcnow().timestamp()) - 3600,
                "end": int(datetime.datetime.utcnow().timestamp()),
                "step": "60s",
            },
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data
    except Exception as e:
        return {"error": str(e)}
    return {"error": "Failed to fetch latency metrics"}


# ========== Service Health Status ==========


@app.get("/services/status")
def get_services_status():
    """Get status of all services"""
    services = [
        {"name": "gateway", "port": 8001},
        {"name": "auth", "port": 8002},
        {"name": "data", "port": 8003},
    ]
    status = []
    for svc in services:
        try:
            resp = requests.get(f"http://localhost:{svc['port']}/health", timeout=2)
            status.append(
                {
                    "name": svc["name"],
                    "status": "UP" if resp.ok else "DOWN",
                    "url": f"http://localhost:{svc['port']}/health",
                }
            )
        except Exception:
            status.append(
                {
                    "name": svc["name"],
                    "status": "DOWN",
                    "url": f"http://localhost:{svc['port']}/health",
                }
            )
    return {"services": status}


# ========== Custom Failure Injection ==========


class CustomFaultRequest(BaseModel):
    fault_type: str  # "latency", "cpu", "network_partition", "stop_service"
    target_service: str
    value: Optional[int] = None  # latency in ms, or cpu percentage
    duration: int = 30


@app.post("/inject/custom")
def inject_custom_fault(req: CustomFaultRequest):
    """Inject a custom fault based on type"""
    results = {}
    container = _container_name(req.target_service)

    try:
        if req.fault_type == "latency" and req.value:
            cmd = [
                "docker-compose",
                "exec",
                "-T",
                req.target_service,
                "tc",
                "qdisc",
                "add",
                "dev",
                "eth0",
                "root",
                "netem",
                "delay",
                f"{req.value}ms",
            ]
            res = subprocess.run(
                cmd, cwd=ROOT, capture_output=True, text=True, timeout=30
            )
            results["latency"] = {
                "rc": res.returncode,
                "stdout": res.stdout,
                "stderr": res.stderr,
            }
            if experiments_collection is not None:
                experiments_collection.insert_one(
                    {
                        "fault_type": "latency",
                        "target_service": req.target_service,
                        "value": req.value,
                        "duration": req.duration,
                        "timestamp": datetime.datetime.utcnow(),
                        "action": "injected",
                    }
                )

        elif req.fault_type == "cpu" and req.value:
            fraction = req.value / 100.0
            cmd = ["docker", "update", "--cpus", str(fraction), container]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            results["cpu"] = {
                "rc": res.returncode,
                "stdout": res.stdout,
                "stderr": res.stderr,
            }
            if experiments_collection is not None:
                experiments_collection.insert_one(
                    {
                        "fault_type": "cpu",
                        "target_service": req.target_service,
                        "value": req.value,
                        "duration": req.duration,
                        "timestamp": datetime.datetime.utcnow(),
                        "action": "injected",
                    }
                )

        elif req.fault_type == "stop_service":
            cmd = ["docker-compose", "stop", req.target_service]
            res = subprocess.run(
                cmd, cwd=ROOT, capture_output=True, text=True, timeout=30
            )
            results["stop"] = {
                "rc": res.returncode,
                "stdout": res.stdout,
                "stderr": res.stderr,
            }
            if experiments_collection is not None:
                experiments_collection.insert_one(
                    {
                        "fault_type": "stop_service",
                        "target_service": req.target_service,
                        "duration": req.duration,
                        "timestamp": datetime.datetime.utcnow(),
                        "action": "injected",
                    }
                )

        elif req.fault_type == "network_partition":
            cmd = [
                "docker-compose",
                "exec",
                "-T",
                req.target_service,
                "iptables",
                "-A",
                "INPUT",
                "-j",
                "DROP",
            ]
            res = subprocess.run(
                cmd, cwd=ROOT, capture_output=True, text=True, timeout=30
            )
            results["network_partition"] = {
                "rc": res.returncode,
                "stdout": res.stdout,
                "stderr": res.stderr,
            }
            if experiments_collection is not None:
                experiments_collection.insert_one(
                    {
                        "fault_type": "network_partition",
                        "target_service": req.target_service,
                        "duration": req.duration,
                        "timestamp": datetime.datetime.utcnow(),
                        "action": "injected",
                    }
                )

        else:
            results["error"] = "Invalid fault type or missing value"
            results["supported_types"] = [
                "latency",
                "cpu",
                "stop_service",
                "network_partition",
            ]

    except subprocess.TimeoutExpired:
        results["error"] = "Command timed out"
    except Exception as e:
        results["error"] = str(e)

    return results


@app.post("/rollback/custom")
def rollback_custom_fault(req: CustomFaultRequest):
    """Rollback a custom fault"""
    results = {}
    container = _container_name(req.target_service)

    try:
        if req.fault_type == "latency":
            cmd = [
                "docker-compose",
                "exec",
                "-T",
                req.target_service,
                "tc",
                "qdisc",
                "del",
                "dev",
                "eth0",
                "root",
                "netem",
            ]
            res = subprocess.run(
                cmd, cwd=ROOT, capture_output=True, text=True, timeout=30
            )
            results["latency"] = {
                "rc": res.returncode,
                "stdout": res.stdout,
                "stderr": res.stderr,
            }

        elif req.fault_type == "cpu":
            cmd = ["docker", "update", container, "--cpus", "2"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            results["cpu"] = {
                "rc": res.returncode,
                "stdout": res.stdout,
                "stderr": res.stderr,
            }

        elif req.fault_type == "stop_service":
            cmd = ["docker-compose", "start", req.target_service]
            res = subprocess.run(
                cmd, cwd=ROOT, capture_output=True, text=True, timeout=30
            )
            results["start"] = {
                "rc": res.returncode,
                "stdout": res.stdout,
                "stderr": res.stderr,
            }

        elif req.fault_type == "network_partition":
            cmd = ["docker", "exec", container, "iptables", "-F", "INPUT"]
            res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            results["network_partition"] = {
                "rc": res.returncode,
                "stdout": res.stdout,
                "stderr": res.stderr,
            }

        else:
            results["error"] = "Invalid fault type"

        if experiments_collection:
            experiments_collection.insert_one(
                {
                    "fault_type": req.fault_type,
                    "target_service": req.target_service,
                    "timestamp": datetime.datetime.utcnow(),
                    "action": "rolled_back",
                }
            )

    except subprocess.TimeoutExpired:
        results["error"] = "Command timed out"
    except Exception as e:
        results["error"] = str(e)

    return results


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
