# ChaosCore

**Distributed Systems Resilience Platform** — Safely inject controlled failures into your infrastructure to proactively discover hidden vulnerabilities before they cause production outages.

---

## What Is This?

ChaosCore is a self-hosted chaos engineering platform. You point it at your services, it discovers what's running, and lets you inject network latency, CPU stress, and container crashes — all with automatic safety aborts, structured logs, experiment history, and AI-generated remediation reports via Gemini.

```
Browser UI  →  Controller (FastAPI)  →  Agent (Python)  →  Target Services
                     ↓                        ↓
                 Prometheus              tc / stress-ng / Docker SDK
```

---

## Architecture

| Component | Tech | Port | Role |
|-----------|------|------|------|
| `controller/` | FastAPI | 8080 | Control plane: agent registry, experiment queue, safety engine |
| `agent/` | Python | — | Data plane: polls controller, executes injections |
| `dashboard/` | React + Vite + Tailwind | 5173 | War Room UI: topology map, live experiment firing |
| `target-app/` | FastAPI (×3) | 8000 | Mock microservices: Gateway → Auth + Data |
| Prometheus | — | 9091 | Scrapes all service metrics |
| Grafana | — | 3001 | Dashboards: System Degradation Index, MTTR Tracker |

---

## Quickstart

### Prerequisites
- Docker + Docker Compose
- A Gemini API key (optional — platform works without it, AI features use mock fallback)

### 1. Configure environment
```bash
cp .env.example .env
# Edit .env and set your GEMINI_API_KEY
```

### 2. Start everything
```bash
docker-compose up -d --build
```

### 3. Open the dashboard
```
http://localhost:5173
```

Wait ~10 seconds for the agent to register. You'll see your containers appear in the topology map.

---

## Running an Experiment

### From the UI
1. Open `http://localhost:5173`
2. Click any container node in the topology map
3. Select a failure type from the **Live Node Inspector** panel
4. Hit **FIRE**

The experiment is queued on the controller, dispatched to the agent on the next heartbeat (≤3s), executed, and auto-reverted after 30 seconds. The **Experiment History** panel updates in real time.

### From the CLI
```bash
python cli/chaos-cli.py run \
  --scenario gateway-latency \
  --target auth-service \
  --delay 200ms \
  --max-mttr 500
```
Exit code `1` if recovery exceeds the MTTR threshold — plugs directly into CI/CD pipelines.

### From the API
```bash
curl -X POST http://localhost:8080/api/v1/experiments/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "name": "network-latency",
    "target_selector": {"container": "auth-service"},
    "parameters": {"delay": "300ms"},
    "duration_seconds": 30
  }'
```

---

## Failure Types

| Capability | What It Does | Injector |
|------------|-------------|----------|
| `simulate_network_delay` | Adds configurable latency on the agent's network interface via `tc netem` | `agent/injectors/network.py` |
| `spike_cpu_memory` | Pegs CPU workers for N seconds via `stress-ng` | `agent/injectors/resource.py` |
| `crash_container` | Sends SIGKILL to a target container via Docker SDK | `agent/injectors/state.py` |

All injections auto-revert after `duration_seconds` (default: 30s). The safety engine continuously monitors Prometheus — if the 503 error rate exceeds 5%, it broadcasts `ABORT_ALL` to all agents.

---

## Autopilot Mode

Toggle **Chaos Autopilot Engine** in the dashboard header. When enabled:

1. Calls Gemini with your live service topology
2. Receives 3 AI-suggested chaos scenarios targeting weak dependency edges
3. Displays a 5-second countdown
4. Auto-fires the first scenario
5. Generates an SRE remediation report post-experiment (`GET /api/v1/ai/report/{experiment_name}`)

Requires `GEMINI_API_KEY` set in `.env`. Without it, a mock scenario is used.

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Controller health check |
| `POST` | `/api/v1/agents/register` | Register a chaos agent |
| `GET` | `/api/v1/agents` | List all connected agents + topology |
| `POST` | `/api/v1/experiments/trigger` | Queue an experiment |
| `GET` | `/api/v1/experiments` | Experiment history (last 50) |
| `POST` | `/api/v1/ai/autopilot/run` | Generate + auto-queue an AI scenario |
| `GET` | `/api/v1/ai/scenarios` | Get AI-suggested chaos scenarios |
| `GET` | `/api/v1/ai/report/{name}` | Post-experiment SRE remediation report |
| `GET` | `/api/v1/score` | Resilience Score (0–100) |

---

## Observability

- **Prometheus**: `http://localhost:9091` — scrapes all target services every 5s
- **Grafana**: `http://localhost:3001` — pre-provisioned dashboards for System Degradation Index and MTTR Tracker (default login: `admin` / `admin`)

---

## Safety

The safety engine (`controller/core/safety_engine.py`) runs on every agent heartbeat:

- Queries Prometheus for live 503 error rate
- If rate exceeds **5%**, broadcasts `ABORT_ALL` — agents immediately revert all active injections
- Thresholds configurable via env vars: `SAFETY_ERROR_THRESHOLD`, `SAFETY_MTTR_MS`
- Fails **open** if Prometheus is unreachable (experiments are not blocked by observability outages)

---

## Project Structure

```
.
├── controller/          # FastAPI orchestrator (control plane)
│   ├── api/
│   │   ├── routes.py    # Agent registry, experiment queue, result reporting
│   │   ├── ai_routes.py # Gemini scenario generation + autopilot
│   │   └── models.py    # Pydantic schemas
│   └── core/
│       ├── safety_engine.py  # Blast-radius abort logic
│       └── ai_analyzer.py    # Gemini API integration
├── agent/               # Chaos agent (data plane)
│   ├── main.py          # Heartbeat loop + experiment dispatcher
│   ├── discovery.py     # Docker + process environment probe
│   └── injectors/
│       ├── network.py   # tc netem latency injection
│       ├── resource.py  # stress-ng CPU stress
│       └── state.py     # Docker container kill/pause
├── dashboard/           # React + Vite + Tailwind UI
├── cli/                 # chaos-cli.py — CI/CD integration
├── target-app/          # Mock microservices (Gateway, Auth, Data)
│   ├── prometheus/      # Prometheus scrape config
│   └── grafana/         # Grafana dashboard provisioning
└── docker-compose.yml
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | — | Google Gemini API key for AI features |
| `CONTROLLER_URL` | `http://controller:8080/api/v1` | Agent → controller URL |
| `PROMETHEUS_URL` | `http://prometheus:9090` | Safety engine Prometheus endpoint |
| `SAFETY_ERROR_THRESHOLD` | `0.05` | 503 rate that triggers auto-abort |
| `SAFETY_MTTR_MS` | `500` | MTTR threshold in milliseconds |
| `LOG_LEVEL` | `INFO` | Python log level (`DEBUG`, `INFO`, `WARNING`) |
