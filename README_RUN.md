Run instructions (quick)

1) Start Docker services (from project root):

```bash
docker-compose build --no-cache
docker-compose up -d
```

2) Start the controller in a virtualenv (recommended):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r framework_controller/requirements.txt
.venv/bin/python -m uvicorn framework_controller.controller:app --host 0.0.0.0 --port 8080 &
```

3) Verify services:

```bash
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
curl http://localhost:9090/targets
```

4) Run the experiment script (example):

```bash
python3 scripts/experiment.py --service auth --rps 20
```

Notes:
- The controller exposes `/inject/stop` and `/rollback/start` to stop/start services by name.
- The experiment script is a simple baseline/demo tool — extend it for more production-like metrics and Prometheus queries.
