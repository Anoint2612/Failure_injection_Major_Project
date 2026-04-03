from fastapi import FastAPI, Response, HTTPException
from prometheus_client import generate_latest, Counter, Histogram
import httpx
import time

app = FastAPI(title="Gateway Service")

REQUEST_COUNT = Counter("gateway_requests_total", "Total Gateway requests")
LATENCY = Histogram("gateway_latency_seconds", "Latency of Gateway requests")

@app.get("/health")
def health():
    return {"status": "ok", "service": "gateway"}

@app.get("/api/data")
async def get_data():
    start = time.time()
    REQUEST_COUNT.inc()
    # Adding a realistic timeout of 5 seconds
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            # Route logic: Authenticate, then fetch data
            auth_res = await client.get("http://auth-service:8000/auth")
            auth_res.raise_for_status()
            
            data_res = await client.get("http://data-service:8000/data")
            data_res.raise_for_status()
            
            result = {"auth": auth_res.json(), "data": data_res.json()}
        except Exception as e:
            LATENCY.observe(time.time() - start)
            raise HTTPException(status_code=503, detail=f"Service unavailable: {str(e)}")
            
    LATENCY.observe(time.time() - start)
    return result

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type="text/plain")
