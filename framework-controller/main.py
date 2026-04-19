"""
Chaos Controller — A generic failure injection framework for microservices.

This is the application entry point. It creates the FastAPI app,
applies middleware, and mounts all routers. No business logic lives here.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import injection, recovery, discovery, experiments, metrics

app = FastAPI(
    title="Chaos Controller",
    description="A generic failure injection framework for microservices",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount feature routers
app.include_router(injection.router)
app.include_router(recovery.router)
app.include_router(discovery.router)
app.include_router(experiments.router)
app.include_router(metrics.router)

@app.get("/api/health")
def health():
    return {"message": "Chaos Controller is Active"}


# ── Serve the built React frontend in production (inside Docker) ──
# In local dev mode, /app/static doesn't exist so this is skipped entirely.
import os
if os.path.isdir("/app/static"):
    from starlette.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory="/app/static", html=True), name="static")
else:
    @app.get("/")
    def root():
        return {"message": "Chaos Controller is Active. Run the frontend separately in dev mode."}