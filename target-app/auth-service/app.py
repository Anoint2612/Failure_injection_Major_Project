from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
import time

app = FastAPI()
Instrumentator().instrument(app).expose(app)
@app.get("/health")
def health():
    return {"status": "healthy", "service": "auth-service"}

@app.get("/validate")
def validate():
    # We will inject latency here later!
    return {"authorized": True, "user": "admin"}