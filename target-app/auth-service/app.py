from fastapi import FastAPI, Response
from prometheus_client import generate_latest, Counter, Histogram
import time

app = FastAPI(title="Auth Service")

REQUEST_COUNT = Counter("auth_requests_total", "Total Auth requests")
LATENCY = Histogram("auth_latency_seconds", "Latency of Auth requests")

@app.get("/health")
def health():
    return {"status": "ok", "service": "auth"}

@app.get("/auth")
def auth():
    start = time.time()
    REQUEST_COUNT.inc()
    time.sleep(0.05) # Simulate minor work
    LATENCY.observe(time.time() - start)
    return {"message": "User Authenticated"}

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type="text/plain")
