# Project Summary: Failure Injection Framework

## What Has Been Done

### 1. Target Microservices (3 Services)
Three FastAPI-based microservices have been created with Prometheus metrics:

| Service | File | Port | Endpoints |
|---------|------|------|-----------|
| Gateway | `target_app/gateway/app.py` | 8001 | `/`, `/health`, `/metrics` |
| Auth | `target_app/auth/app.py` | 8002 | `/login`, `/health`, `/metrics` |
| Data | `target_app/data/app.py` | 8003 | `/items`, `/health`, `/metrics` |

Each service:
- Exposes a health check endpoint
- Tracks request counts with Prometheus Counters
- Has its own `requirements.txt` and `Dockerfile`

### 2. Failure Injection Controller
Located at `framework_controller/controller.py`, this is the core orchestration layer:

**Fault Injection Endpoints:**
- `POST /inject/stop` - Stop services via docker-compose
- `POST /rollback/start` - Start stopped services
- `POST /inject/compound` - Inject network latency and/or CPU limits
- `POST /rollback/compound` - Remove latency and reset CPU limits
- `POST /inject/custom` - Custom fault injection (latency, CPU, network partition, stop)
- `POST /rollback/custom` - Rollback custom faults

**Monitoring Endpoints:**
- `GET /status` - Docker Compose status
- `GET /services/status` - Health of all target services
- `GET /metrics/realtime` - Real-time metrics from Prometheus
- `GET /metrics/latency` - Latency time series data

**Storage Endpoints:**
- `POST /experiments/save` - Save experiment results to MongoDB
- `GET /experiments/history` - Get experiment history from MongoDB
- `GET /reports` - List markdown reports
- `GET /reports/{filename}` - Get specific report

**AI Integration:**
- `POST /run_ai_experiment` - Trigger autonomous experiment runner

### 3. Docker Orchestration
- `docker-compose.yml` orchestrates 4 services:
  - `gateway` (FastAPI + Prometheus client)
  - `auth` (FastAPI + Prometheus client)
  - `data` (FastAPI + Prometheus client)
  - `prometheus` (for metrics collection)

### 4. Prometheus Monitoring
- Config file at `monitoring/prometheus/prometheus.yml`
- Collects metrics from all three target services
- Accessible at `http://localhost:9090`

### 5. Additional Files
- `scenario_generator.py` - Generates failure scenarios
- `autonomous_runner.py` - Runs AI-powered experiments
- `gemini_analyzer.py` - AI analysis component
- `telemetry_exporter.py` - Exports telemetry data
- `scripts/experiment.py` - Basic experiment runner script
- `experiments/scenarios/cascading_stress.json` - Sample scenario

### 6. UI Dashboard
- React-based dashboard in `dashboard/` directory
- `package.json` with dependencies
- Tailwind CSS configured

---

## Architecture Overview

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Gateway   │────▶│    Auth     │────▶│    Data     │
│  (port 8001)│     │  (port 8002)│     │  (port 8003)│
└─────────────┘     └─────────────┘     └─────────────┘
        │                   │                   │
        └───────────────────┴───────────────────┘
                            │
                    ┌───────▼───────┐
                    │  Prometheus   │
                    │ (port 9090)   │
                    └───────────────┘
                            │
        ┌───────────────────┴───────────────────┐
        │                                         │
        ▼                                         ▼
┌───────────────────┐               ┌───────────────────┐
│  MongoDB          │               │   Controller      │
│ (optional)        │               │  (port 8080)      │
└───────────────────┘               │  - Inject faults  │
                                    │  - Monitor        │
                                    │  - Store results  │
                                    └───────────────────┘
```

---

## Key Features Implemented

1. **Service Stop/Start** - Kill or restart services to test resilience
2. **Network Latency Injection** - Add artificial delay to network packets
3. **CPU Throttling** - Limit CPU resources to simulate load
4. **Network Partition** - Block incoming traffic to simulate network failures
5. **Real-time Monitoring** - Query Prometheus for live metrics
6. **Experiment History** - Store and retrieve experiment results from MongoDB
7. **AI-powered Experiments** - Autonomous failure injection and analysis

---

## Running the Project

See `RUN_COMMANDS.md` for step-by-step instructions to run the project.