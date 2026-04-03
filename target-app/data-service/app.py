from fastapi import FastAPI, Response
from prometheus_client import generate_latest, Counter, Histogram
import time
import random

app = FastAPI(title="Data Service")

REQUEST_COUNT = Counter("data_requests_total", "Total Data requests")
LATENCY = Histogram("data_latency_seconds", "Latency of Data requests")

@app.get("/health")
def health():
    return {"status": "ok", "service": "data"}

@app.get("/data")
def data():
    start = time.time()
    REQUEST_COUNT.inc()
    time.sleep(0.1 + random.uniform(0, 0.05)) # Simulated db query
    LATENCY.observe(time.time() - start)
    return {"data": {"users": 1500, "active": 200}}

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type="text/plain")
