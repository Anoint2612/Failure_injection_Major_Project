import logging
import os
import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from api.routes import router
from api.ai_routes import router as ai_router

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] [controller/%(module)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S"
)
logger = logging.getLogger(__name__)

app = FastAPI(title="ChaosCore Orchestrator - Control Plane")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")
app.include_router(ai_router, prefix="/api/v1")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start) * 1000)
    # Only log non-heartbeat calls at INFO to avoid log spam
    path = request.url.path
    if "heartbeat" not in path:
        logger.info(f"{request.method} {path} → {response.status_code} ({duration_ms}ms)")
    else:
        logger.debug(f"{request.method} {path} → {response.status_code} ({duration_ms}ms)")
    return response


@app.on_event("startup")
async def startup():
    logger.info("=" * 60)
    logger.info("ChaosCore Orchestrator starting up")
    logger.info(f"  LOG_LEVEL={os.getenv('LOG_LEVEL', 'INFO')}")
    logger.info(f"  GEMINI_API_KEY={'set' if os.getenv('GEMINI_API_KEY') else 'NOT SET — AI features will use mock'}")
    logger.info(f"  PROMETHEUS_URL={os.getenv('PROMETHEUS_URL', 'http://prometheus:9090')}")
    logger.info("=" * 60)


@app.get("/health")
def health():
    return {"status": "ok", "component": "controller", "version": "2.0.0"}
