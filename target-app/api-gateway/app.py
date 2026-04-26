from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from prometheus_fastapi_instrumentator import Instrumentator
import httpx # We need this to make internal calls
from pydantic import BaseModel, Field
from typing import Optional

app = FastAPI()
Instrumentator().instrument(app).expose(app)
# Internal service URLs (Docker DNS handles the names)
AUTH_URL = "http://auth-service:8001"
DATA_URL = "http://data-service:8002"
ORDERS_URL = "http://orders-service:8003"


class CheckoutRequest(BaseModel):
    item_id: str
    quantity: int = Field(ge=1, le=1000)


def _bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    if not authorization.lower().startswith("bearer "):
        return None
    return authorization.split(" ", 1)[1].strip() or None


@app.get("/health")
def health():
    return {"status": "healthy", "service": "api-gateway"}

@app.get("/", response_class=HTMLResponse)
def home():
    """
    Simple target-app frontend (single HTML page).
    This is intentionally tiny: it creates realistic browser → gateway traffic.
    """
    return """
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Target Shop</title>
    <style>
      body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; background:#0b1220; color:#e6eaf2; margin:0; }
      header { padding:16px 20px; background:#0f1a33; border-bottom:1px solid rgba(255,255,255,0.08); display:flex; justify-content:space-between; align-items:center; }
      .brand { font-weight:700; letter-spacing:0.4px; }
      .wrap { max-width: 980px; margin: 0 auto; padding: 18px 20px; }
      .grid { display:grid; grid-template-columns: 1fr 1fr; gap:16px; }
      .card { background:#101b35; border:1px solid rgba(255,255,255,0.08); border-radius:12px; padding:14px; }
      .row { display:flex; gap:10px; align-items:center; margin:10px 0; }
      input, select { width:100%; padding:10px 10px; border-radius:10px; border:1px solid rgba(255,255,255,0.12); background:#0b1220; color:#e6eaf2; }
      button { padding:10px 12px; border-radius:10px; border:1px solid rgba(255,255,255,0.12); background:#2b5cff; color:white; cursor:pointer; }
      button.secondary { background:#1a274a; }
      pre { white-space:pre-wrap; background:#0b1220; padding:10px; border-radius:10px; border:1px solid rgba(255,255,255,0.08); }
      .small { opacity:0.8; font-size:12px; }
    </style>
  </head>
  <body>
    <header>
      <div class="brand">Target Shop</div>
      <div class="small">api-gateway</div>
    </header>
    <div class="wrap">
      <div class="grid">
        <div class="card">
          <h3>Login (auth-service)</h3>
          <div class="row">
            <input id="user" placeholder="username" value="admin" />
            <input id="pass" placeholder="password" type="password" value="admin" />
          </div>
          <div class="row">
            <button onclick="login()">Login</button>
            <button class="secondary" onclick="whoami()">Who am I?</button>
          </div>
          <div class="small">Token is stored locally in the browser.</div>
        </div>
        <div class="card">
          <h3>Dashboard (gateway → auth + data)</h3>
          <div class="row">
            <button onclick="dashboard()">Refresh dashboard</button>
          </div>
          <pre id="dash">Click refresh.</pre>
        </div>
      </div>

      <div class="card" style="margin-top:16px;">
        <h3>Checkout (gateway → auth validate + data reserve + orders create)</h3>
        <div class="row">
          <input id="item" placeholder="item_id (e.g. sku-1)" value="sku-1" />
          <input id="qty" placeholder="qty" value="1" />
          <button onclick="checkout()">Checkout</button>
          <button class="secondary" onclick="loadOrders()">View Orders</button>
        </div>
        <pre id="checkoutOut">—</pre>
      </div>
    </div>

    <script>
      const API = '';
      const tokenKey = 'targetshop_token';
      const setOut = (id, obj) => document.getElementById(id).textContent = typeof obj === 'string' ? obj : JSON.stringify(obj, null, 2);
      const getToken = () => localStorage.getItem(tokenKey);

      async function login() {
        const username = document.getElementById('user').value;
        const password = document.getElementById('pass').value;
        const r = await fetch(`${API}/api/login`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ username, password }) });
        const d = await r.json();
        if (r.ok && d.token) localStorage.setItem(tokenKey, d.token);
        setOut('checkoutOut', d);
      }
      async function whoami() {
        const token = getToken();
        const r = await fetch(`${API}/api/me`, { headers: token ? { 'Authorization': 'Bearer ' + token } : {} });
        setOut('checkoutOut', await r.json());
      }
      async function dashboard() {
        const r = await fetch(`${API}/dashboard`);
        setOut('dash', await r.json());
      }
      async function checkout() {
        const token = getToken();
        const item_id = document.getElementById('item').value;
        const quantity = parseInt(document.getElementById('qty').value || '1', 10);
        const r = await fetch(`${API}/checkout`, { method:'POST', headers:{'Content-Type':'application/json', ...(token ? {'Authorization':'Bearer ' + token} : {})}, body: JSON.stringify({ item_id, quantity }) });
        setOut('checkoutOut', await r.json());
      }
      async function loadOrders() {
        const r = await fetch(`${API}/orders`);
        setOut('checkoutOut', await r.json());
      }
    </script>
  </body>
</html>
"""

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


@app.post("/api/login")
async def api_login(req: dict):
    """
    Pass-through login to auth-service to create a realistic browser->gateway flow.
    """
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{AUTH_URL}/login", json=req, timeout=5)
        return r.json()


@app.get("/api/me")
async def api_me(authorization: Optional[str] = Header(default=None)):
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{AUTH_URL}/me", headers={"Authorization": authorization} if authorization else {}, timeout=5)
        return r.json()


@app.post("/checkout")
async def checkout(req: CheckoutRequest, authorization: Optional[str] = Header(default=None)):
    """
    Protected-ish operation: validate token with auth-service, then reserve inventory.
    This creates a realistic dependency chain for chaos tests.
    """
    token = _bearer(authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    async with httpx.AsyncClient() as client:
        auth = await client.post(
            f"{AUTH_URL}/validate-token",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        auth_data = auth.json()
        if not auth_data.get("authorized"):
            raise HTTPException(status_code=401, detail="Invalid token")

        reserve = await client.post(
            f"{DATA_URL}/reserve",
            json={"item_id": req.item_id, "quantity": req.quantity},
            timeout=8,
        )
        if reserve.status_code >= 400:
            raise HTTPException(status_code=reserve.status_code, detail=reserve.text)

        order = await client.post(
            f"{ORDERS_URL}/orders",
            json={"user": auth_data.get("user") or "unknown", "item_id": req.item_id, "quantity": req.quantity},
            timeout=8,
        )
        if order.status_code >= 400:
            raise HTTPException(status_code=order.status_code, detail=order.text)

        return {
            "ok": True,
            "user": auth_data.get("user"),
            "reservation": reserve.json(),
            "order": order.json(),
        }


@app.get("/orders")
async def orders(limit: int = 50):
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{ORDERS_URL}/orders", params={"limit": limit}, timeout=5)
        return r.json()