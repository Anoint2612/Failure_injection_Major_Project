from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
import httpx # We need this to make internal calls

app = FastAPI()
Instrumentator().instrument(app).expose(app)
# Internal service URLs (Docker DNS handles the names)
AUTH_URL = "http://auth-service:8001"
DATA_URL = "http://data-service:8002"

@app.get("/health")
def health():
    return {"status": "healthy", "service": "api-gateway"}

@app.get("/dashboard")
async def get_dashboard_data():
    async with httpx.AsyncClient() as client:
        # 1. Check Auth
        auth_res = await client.get(f"{AUTH_URL}/validate")
        # 2. Get Data
        data_res = await client.get(f"{DATA_URL}/items")

        return {
            "user": auth_res.json(),
            "data": data_res.json(),
            "status": "Success"
        }