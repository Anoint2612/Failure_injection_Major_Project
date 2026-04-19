# ChaosController — Failure Injection Platform

An enterprise-grade chaos engineering platform for testing the resilience of containerized microservices. Inject controlled faults — network latency, packet loss, CPU stress, container crashes, and more — then measure impact using a structured 3-phase experiment methodology.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         HOST MACHINE                             │
│                                                                  │
│  ┌──────────────┐     ┌───────────────────────────────────────┐  │
│  │  Frontend     │     │   Docker Compose (Target App)         │  │
│  │  React + Vite │     │  ┌────────────┐   ┌──────────────┐   │  │
│  │  :5173        │────▶│  │api-gateway │──▶│ auth-service  │   │  │
│  └──────┬────────┘     │  │   :8000    │   │   :8001       │   │  │
│         │              │  └─────┬──────┘   └──────────────┘   │  │
│         │              │        │           ┌──────────────┐   │  │
│  ┌──────▼────────┐     │        └──────────▶│ data-service │   │  │
│  │  Controller    │     │                    │   :8002       │   │  │
│  │  FastAPI       │─────│  ┌────────────┐   └──────────────┘   │  │
│  │  :5050         │     │  │ prometheus │   ┌──────────────┐   │  │
│  └───────────────┘     │  │   :9090    │   │   grafana     │   │  │
│                        │  └────────────┘   │   :3000       │   │  │
│                        └───────────────────└──────────────┘───┘  │
└──────────────────────────────────────────────────────────────────┘
```

**Three layers:**

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Target Application** | FastAPI microservices + Prometheus + Grafana | The system under test — any Docker Compose application |
| **Chaos Controller** | FastAPI + Docker SDK for Python | Discovers containers, injects faults via `container.exec_run()`, runs experiments |
| **Dashboard** | React + Vite | Real-time health monitoring, fault catalog, experiment runner with 3-phase results |

---

## Fault Catalog (9 Types)

| Category | Fault | Tool | Description |
|----------|-------|------|-------------|
| **Infrastructure** | Container Crash | Docker SDK `stop()/start()` | Full container stop/restart |
| **Network** | Latency | `tc netem delay` | Adds artificial delay to outbound packets |
| **Network** | Packet Loss | `tc netem loss` | Drops a % of network packets randomly |
| **Network** | Bandwidth Throttle | `tc tbf` | Limits outbound bandwidth (kbit/s) |
| **Network** | Network Partition | `iptables DROP` | Blocks traffic to/from a specific service |
| **Network** | DNS Failure | `/etc/resolv.conf` | Breaks DNS resolution inside a container |
| **Resource** | CPU Stress | `stress-ng --cpu` | Saturates CPU with worker threads |
| **Resource** | Memory Stress | `stress-ng --vm` | Allocates and locks memory blocks |
| **Resource** | Disk I/O Stress | `stress-ng --hdd` | Generates heavy disk write operations |

All faults are **pluggable classes** inheriting from `FaultBase`. Adding a new fault type requires one class — zero router changes.

---

## Experiment Methodology

The experiment runner follows a 3-phase scientific approach:

```
Phase 1: BASELINE         → Measure normal latency (5 requests)
Phase 2: INJECT & MEASURE → Apply fault, measure impact (5 requests)
Phase 3: RECOVER & VERIFY → Remove fault, confirm restoration (5 requests)
```

This provides clear comparative data to identify missing resilience mechanisms (timeouts, circuit breakers, retry policies).

---

## Project Structure

```
.
├── target-app/                     # The application under test
│   ├── api-gateway/                # Gateway service (port 8000)
│   ├── auth-service/               # Auth service (port 8001)
│   ├── data-service/               # Data service (port 8002)
│   ├── monitoring/                 # Prometheus config
│   └── docker-compose.yml
│
├── framework-controller/           # Chaos engine backend
│   ├── main.py                     # FastAPI entry point
│   ├── config.py                   # Environment configuration
│   ├── routers/
│   │   ├── injection.py            # POST /inject/{fault}/{service}
│   │   ├── recovery.py             # POST /recover/{fault}/{service}
│   │   ├── discovery.py            # GET /status
│   │   ├── experiments.py          # POST /experiment/run
│   │   └── metrics.py              # GET /metrics/prometheus
│   ├── services/
│   │   ├── fault_library.py        # Pluggable fault registry (9 types)
│   │   ├── docker_manager.py       # Docker SDK container operations
│   │   ├── experiment_runner.py    # 3-phase experiment engine
│   │   └── health_checker.py       # Service health probing
│   └── requirements.txt
│
└── frontend/                       # React dashboard
    ├── src/
    │   ├── App.jsx                 # Main dashboard component
    │   └── index.css               # Design system (dark/light themes)
    └── index.html
```

---

## Quick Start

### Prerequisites

- **Docker** with Docker Compose
- **Python 3.8+**
- **Node.js 18+** (for the frontend)

### 1. Start the Target Application

```bash
cd target-app
docker compose up --build -d
```

Verify health:
```bash
curl http://localhost:8000/health    # api-gateway
curl http://localhost:8001/health    # auth-service
curl http://localhost:8002/health    # data-service
```

### 2. Start the Chaos Controller

```bash
cd framework-controller
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 5050
```

### 3. Start the Dashboard

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** — the dashboard auto-discovers all running services.

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/status` | Live health check for all discovered services |
| `GET` | `/faults` | Returns the fault catalog with parameter metadata |
| `POST` | `/inject/{fault_name}/{service}` | Inject a fault (e.g., `/inject/latency/data-service?delay_ms=2000`) |
| `POST` | `/recover/{fault_name}/{service}` | Remove a fault and restore normal operation |
| `POST` | `/experiment/run` | Run a 3-phase experiment (baseline → fault → recovery) |
| `GET` | `/metrics/prometheus` | Fetch Prometheus metrics for a service |

---

## Key Design Decisions

### Container-Native Execution
All fault commands (`tc`, `iptables`, `stress-ng`, `kill`) execute **inside Docker containers** via `container.exec_run()`. The host machine is never affected.

### Target-Agnostic Discovery
The controller uses `com.docker.compose.service` labels for dynamic service discovery. It works with **any Docker Compose application** — no configuration needed.

### Docker Desktop Networking
On Docker Desktop (Mac/Windows), `tc netem` rules affect inter-container traffic on the Docker bridge network but **not** host-to-container port-mapped traffic. Inject faults on a **downstream** service and probe via an **upstream** endpoint to observe latency impact.

### Container Requirements
Target containers must include:
- `iproute2` — for `tc` network manipulation
- `stress-ng` — for resource stress testing
- `cap_add: NET_ADMIN` and `privileged: true` in docker-compose.yml

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `tc: RTNETLINK answers: Operation not permitted` | Add `cap_add: NET_ADMIN` and `privileged: true` to the service in docker-compose.yml |
| Services not appearing in dashboard | Verify containers are running: `docker compose ps` |
| Latency test shows no impact | Probe via an upstream gateway (e.g., `http://localhost:8000/dashboard`), not the target service directly |
| Health check shows DOWN after latency injection | Expected if delay > health timeout (15s). Click Recover to clear rules |
| Frontend won't start | Run `cd frontend && npm install && npm run dev` |
| `stress-ng` not found | Add `RUN apt-get update && apt-get install -y stress-ng` to the target Dockerfile |