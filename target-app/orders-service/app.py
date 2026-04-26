from fastapi import FastAPI, HTTPException
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field
import time
import uuid
import random

app = FastAPI(title="orders-service", version="1.0.0")
Instrumentator().instrument(app).expose(app)

# In-memory orders store (target app only)
_ORDERS: dict[str, dict] = {}


class CreateOrderRequest(BaseModel):
    user: str = Field(min_length=1, max_length=100)
    item_id: str = Field(min_length=1, max_length=200)
    quantity: int = Field(ge=1, le=1000)


@app.get("/health")
def health():
    return {"status": "healthy", "service": "orders-service"}


@app.post("/orders")
def create_order(req: CreateOrderRequest):
    """
    Create an order. Adds small jitter to simulate DB work.
    """
    time.sleep(random.uniform(0.02, 0.12))
    order_id = f"ord-{uuid.uuid4().hex[:10]}"
    order = {
        "id": order_id,
        "user": req.user,
        "item_id": req.item_id,
        "quantity": int(req.quantity),
        "status": "created",
        "created_at": time.time(),
    }
    _ORDERS[order_id] = order
    return order


@app.get("/orders")
def list_orders(limit: int = 50):
    limit = max(1, min(int(limit), 200))
    all_orders = list(_ORDERS.values())
    # newest first
    all_orders.sort(key=lambda o: o.get("created_at", 0), reverse=True)
    return {"orders": all_orders[:limit], "count": len(all_orders)}


@app.get("/orders/{order_id}")
def get_order(order_id: str):
    o = _ORDERS.get(order_id)
    if not o:
        raise HTTPException(status_code=404, detail="Order not found")
    return o

