from fastapi import FastAPI, HTTPException
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field
import random
import time
import uuid
from typing import Optional

app = FastAPI()
Instrumentator().instrument(app).expose(app)

# In-memory "catalog" (target app only)
_ITEMS: dict[str, dict] = {
    "sku-1": {"id": "sku-1", "name": "Disk_A", "price": 19.99, "stock": 10},
    "sku-2": {"id": "sku-2", "name": "Disk_B", "price": 29.99, "stock": 7},
    "sku-3": {"id": "sku-3", "name": "Disk_C", "price": 9.99, "stock": 25},
}


class CreateItemRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    price: float = Field(gt=0, lt=100000)
    stock: int = Field(ge=0, le=100000)


class UpdateItemRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    price: Optional[float] = Field(default=None, gt=0, lt=100000)
    stock: Optional[int] = Field(default=None, ge=0, le=100000)


class ReserveRequest(BaseModel):
    item_id: str
    quantity: int = Field(ge=1, le=1000)


@app.get("/health")
def health():
    return {"status": "healthy", "service": "data-service"}

@app.get("/items")
def get_items():
    # In a real app, this would fetch from a DB. 
    # We will use this to test "Resource Exhaustion" later.
    return {"items": list(_ITEMS.values()), "db_status": "connected"}


@app.get("/items/{item_id}")
def get_item(item_id: str):
    item = _ITEMS.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@app.post("/items")
def create_item(req: CreateItemRequest):
    item_id = f"sku-{uuid.uuid4().hex[:8]}"
    item = {"id": item_id, "name": req.name, "price": float(req.price), "stock": int(req.stock)}
    _ITEMS[item_id] = item
    return item


@app.put("/items/{item_id}")
def update_item(item_id: str, req: UpdateItemRequest):
    item = _ITEMS.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if req.name is not None:
        item["name"] = req.name
    if req.price is not None:
        item["price"] = float(req.price)
    if req.stock is not None:
        item["stock"] = int(req.stock)
    return item


@app.post("/reserve")
def reserve(req: ReserveRequest):
    """
    Simple reservation endpoint to create realistic state changes.
    """
    item = _ITEMS.get(req.item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if item["stock"] < req.quantity:
        raise HTTPException(status_code=409, detail="Insufficient stock")

    # Simulate a small DB delay/jitter
    time.sleep(random.uniform(0.01, 0.08))
    item["stock"] -= req.quantity
    return {"reserved": True, "item_id": req.item_id, "quantity": req.quantity, "remaining": item["stock"]}