# Running the Failure Injection Project

## Prerequisites
- Docker and Docker Compose installed
- Python 3.8+ installed
- MongoDB (optional, for experiment storage)

---

## Step 1: Build and Start Docker Services

```bash
# Navigate to project root
cd /Users/ankit/Desktop/Failure_injection_Major_Project

# Build and start all services (gateway, auth, data, prometheus)
docker-compose build --no-cache
docker-compose up -d
```

## Step 2: Verify Docker Services are Running

```bash
# Check container status
docker-compose ps

# Test health endpoints
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health

# Check Prometheus
curl http://localhost:9090/-/healthy
```

## Step 3: Set Up Python Virtual Environment

```bash
# Create virtual environment (if not already created)
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Install controller dependencies
pip install -r framework_controller/requirements.txt
```

## Step 4: Start the Controller

```bash
# Run the controller on port 8080
.venv/bin/python -m uvicorn framework_controller.controller:app --host 0.0.0.0 --port 8080 &

# Or without background (&), in a separate terminal:
# .venv/bin/python -m uvicorn framework_controller.controller:app --host 0.0.0.0 --port 8080
```

## Step 5: Verify Controller is Running

```bash
# Test controller endpoints
curl http://localhost:8080/services/status
curl http://localhost:8080/status
```

---

## Usage Examples

### Inject Faults via Controller

```bash
# Stop a service
curl -X POST http://localhost:8080/inject/stop -H "Content-Type: application/json" -d '{"services": ["auth"]}'

# Start (rollback) a service
curl -X POST http://localhost:8080/rollback/start -H "Content-Type: application/json" -d '{"services": ["auth"]}'

# Inject latency on a service (e.g., 2000ms on gateway)
curl -X POST http://localhost:8080/inject/compound -H "Content-Type: application/json" -d '{"latency_ms": 2000, "latency_target": "gateway"}'

# Inject CPU limit on a service (e.g., 10% CPU on auth)
curl -X POST http://localhost:8080/inject/compound -H "Content-Type: application/json" -d '{"cpu_exhaustion_percent": 10, "cpu_target": "auth"}'

# Custom fault injection
curl -X POST http://localhost:8080/inject/custom -H "Content-Type: application/json" -d '{"fault_type": "latency", "target_service": "gateway", "value": 3000, "duration": 30}'

# Rollback custom fault
curl -X POST http://localhost:8080/rollback/custom -H "Content-Type: application/json" -d '{"fault_type": "latency", "target_service": "gateway"}'
```

### Get Metrics

```bash
# Real-time metrics from Prometheus
curl http://localhost:8080/metrics/realtime

# Service status
curl http://localhost:8080/services/status
```

### Run Experiment Script

```bash
# Run experiment on a service
python3 scripts/experiment.py --service auth --rps 20
```

---

## Access Points

| Service | URL |
|---------|-----|
| Gateway | http://localhost:8001 |
| Auth | http://localhost:8002 |
| Data | http://localhost:8003 |
| Prometheus | http://localhost:9090 |
| Controller API | http://localhost:8080 |

---

## Stopping the Project

```bash
# Stop Docker services
docker-compose down

# Stop the controller (if running in background)
pkill -f "uvicorn framework_controller.controller"
```