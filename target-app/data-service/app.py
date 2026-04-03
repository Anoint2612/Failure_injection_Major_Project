from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
import random

app = FastAPI()
Instrumentator().instrument(app).expose(app)
@app.get("/health")
def health():
    return {"status": "healthy", "service": "data-service"}

@app.get("/items")
def get_items():
    # In a real app, this would fetch from a DB. 
    # We will use this to test "Resource Exhaustion" later.
    return {"items": ["Disk_A", "Disk_B", "Disk_C"], "db_status": "connected"}