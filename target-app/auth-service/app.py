from fastapi import FastAPI, Header, HTTPException
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel
import time
import uuid
from typing import Optional

app = FastAPI()
Instrumentator().instrument(app).expose(app)

# Very small in-memory "auth" store (target app only)
_TOKENS: dict[str, dict] = {}


class LoginRequest(BaseModel):
    username: str
    password: str


def _issue_token(username: str) -> str:
    token = uuid.uuid4().hex
    _TOKENS[token] = {"user": username, "issued_at": time.time()}
    return token


def _get_bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    if not authorization.lower().startswith("bearer "):
        return None
    return authorization.split(" ", 1)[1].strip() or None


@app.get("/health")
def health():
    return {"status": "healthy", "service": "auth-service"}

@app.get("/validate")
def validate():
    # We will inject latency here later!
    return {"authorized": True, "user": "admin"}


@app.post("/login")
def login(req: LoginRequest):
    """
    Dummy login endpoint to create a realistic POST payload surface.
    Accepts any username/password and returns a bearer token.
    """
    token = _issue_token(req.username)
    return {"token": token, "token_type": "bearer", "user": req.username}


@app.get("/me")
def me(authorization: Optional[str] = Header(default=None)):
    """
    Protected endpoint (requires Authorization: Bearer <token>).
    """
    token = _get_bearer_token(authorization)
    if not token or token not in _TOKENS:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {"user": _TOKENS[token]["user"], "issued_at": _TOKENS[token]["issued_at"]}


@app.post("/validate-token")
def validate_token(authorization: Optional[str] = Header(default=None)):
    """
    Used by api-gateway to validate a bearer token.
    """
    token = _get_bearer_token(authorization)
    if not token or token not in _TOKENS:
        return {"authorized": False}
    return {"authorized": True, "user": _TOKENS[token]["user"]}