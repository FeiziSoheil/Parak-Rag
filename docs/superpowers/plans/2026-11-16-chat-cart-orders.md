# Chat Cart + Simple Orders Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let logged-in users add products to a server-side cart from chat (sidebar + cards), edit the cart in a header Sheet, and place a `pending` order with a short checkout form (no payment, no catalog page).

**Architecture:** SQLite tables `cart_items`, `orders`, `order_items` with snapshot fields; FastAPI JWT routers `/api/cart` and `/api/orders`; Next.js `CartProvider` + header badge/Sheet; ProductSidebar variant select + Add to cart; chat cards quick-add (or open sidebar when variants exist).

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, pytest + httpx TestClient, Next.js 14, TypeScript, shadcn Sheet, sonner toasts.

**Spec:** `docs/superpowers/specs/2026-11-16-chat-cart-orders-design.md`

## Global Constraints

- Logged-in users only (JWT via existing `get_current_user`)
- No payment gateway, no catalog page, no “My orders” UI, no guest cart
- No-variant lines store `variant_label=""` (not SQL NULL)
- Checkout blocked if any cart line has `unit_price is None`
- Empty cart checkout → `400`
- PATCH quantity must be ≥ 1; delete only via DELETE
- Cross-user cart item access → `404`
- Follow existing patterns in `backend/app/api/auth.py`, `frontend/lib/api.ts`, `frontend/app/(dashboard)/chat/page.tsx`

## File structure (create / modify)

| Path | Responsibility |
|------|----------------|
| `backend/app/models/cart.py` | `CartItem` model |
| `backend/app/models/order.py` | `Order`, `OrderItem` models |
| `backend/app/models/__init__.py` | Export new models |
| `backend/app/models/user.py` | Optional relationships |
| `backend/app/schemas/cart.py` | Cart request/response schemas |
| `backend/app/schemas/order.py` | Order request/response schemas |
| `backend/app/api/cart.py` | Cart CRUD endpoints |
| `backend/app/api/orders.py` | Checkout endpoint |
| `backend/app/main.py` | Import models + include routers |
| `backend/tests/conftest.py` | Slim test app + fixtures (no CLIP/Whisper lifespan) |
| `backend/tests/test_cart.py` | Cart API tests |
| `backend/tests/test_orders.py` | Orders API tests |
| `frontend/lib/api.ts` | Cart/order client types + fetch helpers |
| `frontend/contexts/CartContext.tsx` | `CartProvider` + hooks |
| `frontend/components/cart/CartSheet.tsx` | Sheet: list + checkout form steps |
| `frontend/components/cart/CartHeaderButton.tsx` | Icon + badge + opens sheet |
| `frontend/app/(dashboard)/chat/layout.tsx` | Wrap with `CartProvider` |
| `frontend/app/(dashboard)/chat/page.tsx` | Mount `CartHeaderButton` in header |
| `frontend/components/chat/ProductSidebar.tsx` | Variant select + Add to cart |
| `frontend/components/chat/MessageList.tsx` | Quick add / open sidebar for variants |
| `frontend/components/chat/ChatPanel.tsx` | Pass cart-related callbacks into list/sidebar |

---

### Task 1: Backend models + schemas + test harness

**Files:**
- Create: `backend/app/models/cart.py`
- Create: `backend/app/models/order.py`
- Create: `backend/app/schemas/cart.py`
- Create: `backend/app/schemas/order.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_models_smoke.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/models/user.py`
- Modify: `backend/requirements.txt` (add `pytest`)
- Test: `backend/tests/test_models_smoke.py`

**Interfaces:**
- Consumes: `Base` from `app.core.database`; `User` model
- Produces:
  - `CartItem(user_id, product_id, subject, unit_price, image_url, category_name, variant_label, quantity)`
  - `Order(user_id, status, recipient_name, phone, address, note, total_amount)`
  - `OrderItem(order_id, product_id, subject, unit_price, image_url, category_name, variant_label, quantity)`
  - Schemas: `CartItemCreate`, `CartItemUpdate`, `CartItemOut`, `CartOut`, `OrderCreate`, `OrderOut`

- [ ] **Step 1: Add pytest dependency**

Append to `backend/requirements.txt`:

```
pytest>=8.0.0
```

Run from `backend/`:

```bash
./venv/bin/pip install pytest>=8.0.0
```

Expected: install succeeds (use project venv if present).

- [ ] **Step 2: Write failing smoke test (models import + table create)**

Create `backend/tests/test_models_smoke.py`:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models import User, CartItem, Order, OrderItem  # noqa: F401


def test_cart_order_tables_create():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    user = User(username="u1", password_hash="x")
    db.add(user)
    db.commit()
    db.refresh(user)
    item = CartItem(
        user_id=user.id,
        product_id=42,
        subject="Widget",
        unit_price=9.99,
        image_url=None,
        category_name="Gadgets",
        variant_label="",
        quantity=2,
    )
    db.add(item)
    db.commit()
    assert db.query(CartItem).count() == 1
    db.close()
```

- [ ] **Step 3: Run test — expect FAIL (import error)**

```bash
cd backend && ./venv/bin/python -m pytest tests/test_models_smoke.py -v
```

Expected: FAIL — `CartItem` / `Order` not exportable yet.

- [ ] **Step 4: Implement models**

`backend/app/models/cart.py`:

```python
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id", "variant_label", name="uq_cart_user_product_variant"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    product_id = Column(Integer, nullable=False, index=True)
    subject = Column(String(1024), nullable=False)
    unit_price = Column(Float, nullable=True)
    image_url = Column(String(2048), nullable=True)
    category_name = Column(String(512), nullable=False, default="")
    variant_label = Column(String(512), nullable=False, default="")
    quantity = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="cart_items")
```

`backend/app/models/order.py`:

```python
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    status = Column(String(64), nullable=False, default="pending")
    recipient_name = Column(String(255), nullable=False)
    phone = Column(String(64), nullable=False)
    address = Column(Text, nullable=False)
    note = Column(Text, nullable=True)
    total_amount = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    product_id = Column(Integer, nullable=False)
    subject = Column(String(1024), nullable=False)
    unit_price = Column(Float, nullable=False)
    image_url = Column(String(2048), nullable=True)
    category_name = Column(String(512), nullable=False, default="")
    variant_label = Column(String(512), nullable=False, default="")
    quantity = Column(Integer, nullable=False)

    order = relationship("Order", back_populates="items")
```

Update `backend/app/models/__init__.py`:

```python
from app.models.user import User
from app.models.session import ChatSession
from app.models.message import Message
from app.models.store_info import StoreInfo
from app.models.faq import FAQ
from app.models.cart import CartItem
from app.models.order import Order, OrderItem

__all__ = [
    "User",
    "ChatSession",
    "Message",
    "StoreInfo",
    "FAQ",
    "CartItem",
    "Order",
    "OrderItem",
]
```

In `backend/app/models/user.py`, add relationships (keep existing fields):

```python
cart_items = relationship("CartItem", back_populates="user")
orders = relationship("Order", back_populates="user")
```

- [ ] **Step 5: Implement schemas**

`backend/app/schemas/cart.py`:

```python
from pydantic import BaseModel, Field


class CartItemCreate(BaseModel):
    product_id: int
    subject: str
    unit_price: float | None = None
    image_url: str | None = None
    category_name: str = ""
    variant_label: str = ""
    quantity: int = Field(default=1, ge=1)


class CartItemUpdate(BaseModel):
    quantity: int = Field(ge=1)


class CartItemOut(BaseModel):
    id: int
    product_id: int
    subject: str
    unit_price: float | None
    image_url: str | None
    category_name: str
    variant_label: str
    quantity: int

    model_config = {"from_attributes": True}


class CartOut(BaseModel):
    items: list[CartItemOut]
    item_count: int
    subtotal: float | None
    checkout_ready: bool
```

`backend/app/schemas/order.py`:

```python
from datetime import datetime

from pydantic import BaseModel, Field


class OrderCreate(BaseModel):
    recipient_name: str = Field(min_length=1)
    phone: str = Field(min_length=1)
    address: str = Field(min_length=1)
    note: str | None = None


class OrderItemOut(BaseModel):
    id: int
    product_id: int
    subject: str
    unit_price: float
    image_url: str | None
    category_name: str
    variant_label: str
    quantity: int

    model_config = {"from_attributes": True}


class OrderOut(BaseModel):
    id: int
    status: str
    recipient_name: str
    phone: str
    address: str
    note: str | None
    total_amount: float
    created_at: datetime
    items: list[OrderItemOut]

    model_config = {"from_attributes": True}
```

- [ ] **Step 6: Stub routers so conftest/imports work**

`backend/app/api/cart.py`:

```python
from fastapi import APIRouter

router = APIRouter()
```

`backend/app/api/orders.py`:

```python
from fastapi import APIRouter

router = APIRouter()
```

- [ ] **Step 7: Create conftest slim app (for later API tasks)**

`backend/tests/conftest.py`:

```python
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import create_access_token, get_password_hash
from app.models import User, CartItem, Order, OrderItem  # noqa: F401
from app.api import auth
from app.api import cart as cart_api
from app.api import orders as orders_api


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app = FastAPI()
    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(cart_api.router, prefix="/api", tags=["cart"])
    app.include_router(orders_api.router, prefix="/api", tags=["orders"])
    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def user_a(db_session):
    u = User(username="alice", password_hash=get_password_hash("password123"), email_verified=True)
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


@pytest.fixture()
def user_b(db_session):
    u = User(username="bob", password_hash=get_password_hash("password123"), email_verified=True)
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


@pytest.fixture()
def auth_header_a(user_a):
    token = create_access_token({"sub": user_a.username})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def auth_header_b(user_b):
    token = create_access_token({"sub": user_b.username})
    return {"Authorization": f"Bearer {token}"}
```

Real cart/order endpoints are filled in Tasks 2–3; stubs from Step 6 keep imports valid.

- [ ] **Step 8: Re-run smoke test — expect PASS**

```bash
cd backend && ./venv/bin/python -m pytest tests/test_models_smoke.py -v
```

Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add backend/app/models/cart.py backend/app/models/order.py backend/app/models/__init__.py backend/app/models/user.py backend/app/schemas/cart.py backend/app/schemas/order.py backend/app/api/cart.py backend/app/api/orders.py backend/tests/conftest.py backend/tests/test_models_smoke.py backend/requirements.txt
git commit -m "$(cat <<'EOF'
feat: add cart/order models and test harness

EOF
)"
```

---

### Task 2: Cart API

**Files:**
- Modify: `backend/app/api/cart.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_cart.py`
- Test: `backend/tests/test_cart.py`

**Interfaces:**
- Consumes: `CartItem`, `CartItemCreate`, `CartItemUpdate`, `CartOut`, `get_current_user`, `get_db`
- Produces:
  - `GET /api/cart` → `CartOut`
  - `POST /api/cart/items` → `CartItemOut` (upsert by user+product+variant_label)
  - `PATCH /api/cart/items/{id}` → `CartItemOut`
  - `DELETE /api/cart/items/{id}` → `204`
  - Helper used by orders later: compute `item_count`, `subtotal`, `checkout_ready` where `checkout_ready = len(items)>0 and all(i.unit_price is not None for i in items)` and `subtotal = sum(i.unit_price * i.quantity for i in items if i.unit_price is not None)` (only meaningful when checkout_ready)

- [ ] **Step 1: Write failing cart tests**

`backend/tests/test_cart.py`:

```python
SAMPLE = {
    "product_id": 101,
    "subject": "Blue Mug",
    "unit_price": 12.5,
    "image_url": "https://example.com/mug.jpg",
    "category_name": "Home",
    "variant_label": "",
    "quantity": 1,
}


def test_cart_requires_auth(client):
    assert client.get("/api/cart").status_code == 401


def test_add_get_patch_delete(client, auth_header_a):
    r = client.post("/api/cart/items", json=SAMPLE, headers=auth_header_a)
    assert r.status_code == 200
    item = r.json()
    assert item["quantity"] == 1
    assert item["product_id"] == 101

    r2 = client.post("/api/cart/items", json=SAMPLE, headers=auth_header_a)
    assert r2.status_code == 200
    assert r2.json()["quantity"] == 2
    assert r2.json()["id"] == item["id"]

    cart = client.get("/api/cart", headers=auth_header_a).json()
    assert cart["item_count"] == 2
    assert cart["subtotal"] == 25.0
    assert cart["checkout_ready"] is True

    patched = client.patch(
        f"/api/cart/items/{item['id']}",
        json={"quantity": 3},
        headers=auth_header_a,
    )
    assert patched.status_code == 200
    assert patched.json()["quantity"] == 3

    bad = client.patch(
        f"/api/cart/items/{item['id']}",
        json={"quantity": 0},
        headers=auth_header_a,
    )
    assert bad.status_code == 422 or bad.status_code == 400

    deleted = client.delete(f"/api/cart/items/{item['id']}", headers=auth_header_a)
    assert deleted.status_code == 204
    cart2 = client.get("/api/cart", headers=auth_header_a).json()
    assert cart2["items"] == []
    assert cart2["item_count"] == 0


def test_null_price_not_checkout_ready(client, auth_header_a):
    payload = {**SAMPLE, "unit_price": None}
    client.post("/api/cart/items", json=payload, headers=auth_header_a)
    cart = client.get("/api/cart", headers=auth_header_a).json()
    assert cart["checkout_ready"] is False


def test_cart_isolation(client, auth_header_a, auth_header_b):
    r = client.post("/api/cart/items", json=SAMPLE, headers=auth_header_a)
    item_id = r.json()["id"]
    assert client.get("/api/cart", headers=auth_header_b).json()["items"] == []
    assert client.delete(f"/api/cart/items/{item_id}", headers=auth_header_b).status_code == 404
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd backend && ./venv/bin/python -m pytest tests/test_cart.py -v
```

Expected: FAIL (404 / missing routes).

- [ ] **Step 3: Implement cart router**

Replace `backend/app/api/cart.py` with:

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.cart import CartItem
from app.models.user import User
from app.schemas.cart import CartItemCreate, CartItemUpdate, CartItemOut, CartOut

router = APIRouter()


def _normalize_variant(label: str | None) -> str:
    return (label or "").strip()


def serialize_cart(items: list[CartItem]) -> CartOut:
    outs = [CartItemOut.model_validate(i) for i in items]
    item_count = sum(i.quantity for i in items)
    checkout_ready = len(items) > 0 and all(i.unit_price is not None for i in items)
    subtotal = None
    if checkout_ready:
        subtotal = float(sum((i.unit_price or 0) * i.quantity for i in items))
    return CartOut(items=outs, item_count=item_count, subtotal=subtotal, checkout_ready=checkout_ready)


@router.get("/cart", response_model=CartOut)
def get_cart(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items = db.query(CartItem).filter(CartItem.user_id == current_user.id).order_by(CartItem.id).all()
    return serialize_cart(items)


@router.post("/cart/items", response_model=CartItemOut)
def add_cart_item(
    body: CartItemCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    variant = _normalize_variant(body.variant_label)
    existing = (
        db.query(CartItem)
        .filter(
            CartItem.user_id == current_user.id,
            CartItem.product_id == body.product_id,
            CartItem.variant_label == variant,
        )
        .first()
    )
    if existing:
        existing.quantity += body.quantity
        existing.subject = body.subject
        existing.unit_price = body.unit_price
        existing.image_url = body.image_url
        existing.category_name = body.category_name or ""
        db.commit()
        db.refresh(existing)
        return existing

    item = CartItem(
        user_id=current_user.id,
        product_id=body.product_id,
        subject=body.subject,
        unit_price=body.unit_price,
        image_url=body.image_url,
        category_name=body.category_name or "",
        variant_label=variant,
        quantity=body.quantity,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/cart/items/{item_id}", response_model=CartItemOut)
def update_cart_item(
    item_id: int,
    body: CartItemUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = (
        db.query(CartItem)
        .filter(CartItem.id == item_id, CartItem.user_id == current_user.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found")
    item.quantity = body.quantity
    db.commit()
    db.refresh(item)
    return item


@router.delete("/cart/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cart_item(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = (
        db.query(CartItem)
        .filter(CartItem.id == item_id, CartItem.user_id == current_user.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cart item not found")
    db.delete(item)
    db.commit()
    return None
```

In `backend/app/main.py`:

1. Extend the models import so tables are registered:

```python
from app.models import User, ChatSession, Message, StoreInfo, FAQ, CartItem, Order, OrderItem  # noqa: F401
```

2. Import and include routers:

```python
from app.api import auth, chat, ingest, search as search_api, settings as settings_api, cart as cart_api, orders as orders_api
```

```python
app.include_router(cart_api.router, prefix="/api", tags=["cart"])
app.include_router(orders_api.router, prefix="/api", tags=["orders"])
```

- [ ] **Step 4: Run cart tests — expect PASS**

```bash
cd backend && ./venv/bin/python -m pytest tests/test_cart.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/cart.py backend/app/main.py backend/tests/test_cart.py
git commit -m "$(cat <<'EOF'
feat: add authenticated cart API

EOF
)"
```

---

### Task 3: Orders API (checkout)

**Files:**
- Modify: `backend/app/api/orders.py`
- Create: `backend/tests/test_orders.py`
- Test: `backend/tests/test_orders.py`

**Interfaces:**
- Consumes: cart rows for `current_user`; `OrderCreate` → `OrderOut`
- Produces: `POST /api/orders` creates order+items, clears cart, returns `OrderOut` with `status="pending"`

- [ ] **Step 1: Write failing order tests**

`backend/tests/test_orders.py`:

```python
SAMPLE = {
    "product_id": 101,
    "subject": "Blue Mug",
    "unit_price": 10.0,
    "image_url": None,
    "category_name": "Home",
    "variant_label": "Color: Blue",
    "quantity": 2,
}

CHECKOUT = {
    "recipient_name": "Alice",
    "phone": "+98912",
    "address": "Tehran",
    "note": "Leave at door",
}


def test_checkout_empty_cart(client, auth_header_a):
    r = client.post("/api/orders", json=CHECKOUT, headers=auth_header_a)
    assert r.status_code == 400


def test_checkout_rejects_null_price(client, auth_header_a):
    client.post("/api/cart/items", json={**SAMPLE, "unit_price": None}, headers=auth_header_a)
    r = client.post("/api/orders", json=CHECKOUT, headers=auth_header_a)
    assert r.status_code == 400


def test_checkout_success_clears_cart(client, auth_header_a):
    client.post("/api/cart/items", json=SAMPLE, headers=auth_header_a)
    r = client.post("/api/orders", json=CHECKOUT, headers=auth_header_a)
    assert r.status_code == 200
    order = r.json()
    assert order["status"] == "pending"
    assert order["total_amount"] == 20.0
    assert len(order["items"]) == 1
    assert order["items"][0]["variant_label"] == "Color: Blue"
    assert order["recipient_name"] == "Alice"
    cart = client.get("/api/cart", headers=auth_header_a).json()
    assert cart["items"] == []
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd backend && ./venv/bin/python -m pytest tests/test_orders.py -v
```

Expected: FAIL (route missing / 404).

- [ ] **Step 3: Implement orders router**

Replace `backend/app/api/orders.py` with:

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.cart import CartItem
from app.models.order import Order, OrderItem
from app.models.user import User
from app.schemas.order import OrderCreate, OrderOut

router = APIRouter()


@router.post("/orders", response_model=OrderOut)
def create_order(
    body: OrderCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items = db.query(CartItem).filter(CartItem.user_id == current_user.id).all()
    if not items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cart is empty")
    if any(i.unit_price is None for i in items):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cart has items without price",
        )

    total = float(sum((i.unit_price or 0) * i.quantity for i in items))
    order = Order(
        user_id=current_user.id,
        status="pending",
        recipient_name=body.recipient_name.strip(),
        phone=body.phone.strip(),
        address=body.address.strip(),
        note=(body.note.strip() if body.note else None),
        total_amount=total,
    )
    db.add(order)
    db.flush()

    for i in items:
        db.add(
            OrderItem(
                order_id=order.id,
                product_id=i.product_id,
                subject=i.subject,
                unit_price=float(i.unit_price),
                image_url=i.image_url,
                category_name=i.category_name or "",
                variant_label=i.variant_label or "",
                quantity=i.quantity,
            )
        )
        db.delete(i)

    db.commit()
    db.refresh(order)
    # ensure items loaded
    _ = order.items
    return order
```

- [ ] **Step 4: Run order + cart tests — expect PASS**

```bash
cd backend && ./venv/bin/python -m pytest tests/test_cart.py tests/test_orders.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/orders.py backend/tests/test_orders.py
git commit -m "$(cat <<'EOF'
feat: add checkout orders API from cart

EOF
)"
```

---

### Task 4: Frontend API client + CartProvider

**Files:**
- Modify: `frontend/lib/api.ts`
- Create: `frontend/contexts/CartContext.tsx`
- Modify: `frontend/app/(dashboard)/chat/layout.tsx`
- Test: manual TypeScript check / `npm run lint` scoped if available

**Interfaces:**
- Consumes: JWT via existing `getToken()`; backend shapes from Task 2–3
- Produces:
  - Types: `CartItem`, `Cart`, `OrderCreate`, `Order`
  - Functions: `getCart()`, `addCartItem(input)`, `updateCartItem(id, quantity)`, `deleteCartItem(id)`, `createOrder(body)`
  - `useCart()` → `{ cart, loading, refresh, addItem, setQuantity, removeItem, checkout, open, setOpen }`

- [ ] **Step 1: Add API helpers at end of `frontend/lib/api.ts`**

```typescript
export type CartItem = {
  id: number;
  product_id: number;
  subject: string;
  unit_price: number | null;
  image_url: string | null;
  category_name: string;
  variant_label: string;
  quantity: number;
};

export type Cart = {
  items: CartItem[];
  item_count: number;
  subtotal: number | null;
  checkout_ready: boolean;
};

export type CartItemCreateInput = {
  product_id: number;
  subject: string;
  unit_price: number | null;
  image_url: string | null;
  category_name: string;
  variant_label?: string;
  quantity?: number;
};

export type OrderCreateInput = {
  recipient_name: string;
  phone: string;
  address: string;
  note?: string | null;
};

export type OrderItem = {
  id: number;
  product_id: number;
  subject: string;
  unit_price: number;
  image_url: string | null;
  category_name: string;
  variant_label: string;
  quantity: number;
};

export type Order = {
  id: number;
  status: string;
  recipient_name: string;
  phone: string;
  address: string;
  note: string | null;
  total_amount: number;
  created_at: string;
  items: OrderItem[];
};

export async function getCart(): Promise<Cart> {
  const token = getToken();
  if (!token) throw new Error("Not authenticated");
  const res = await fetch(`${API_BASE}/api/cart`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Failed to load cart");
  return res.json();
}

export async function addCartItem(input: CartItemCreateInput): Promise<CartItem> {
  const token = getToken();
  if (!token) throw new Error("Not authenticated");
  const res = await fetch(`${API_BASE}/api/cart/items`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      variant_label: "",
      quantity: 1,
      ...input,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Failed to add to cart");
  }
  return res.json();
}

export async function updateCartItem(itemId: number, quantity: number): Promise<CartItem> {
  const token = getToken();
  if (!token) throw new Error("Not authenticated");
  const res = await fetch(`${API_BASE}/api/cart/items/${itemId}`, {
    method: "PATCH",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ quantity }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Failed to update cart");
  }
  return res.json();
}

export async function deleteCartItem(itemId: number): Promise<void> {
  const token = getToken();
  if (!token) throw new Error("Not authenticated");
  const res = await fetch(`${API_BASE}/api/cart/items/${itemId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Failed to remove item");
  }
}

export async function createOrder(body: OrderCreateInput): Promise<Order> {
  const token = getToken();
  if (!token) throw new Error("Not authenticated");
  const res = await fetch(`${API_BASE}/api/orders`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Checkout failed");
  }
  return res.json();
}
```

- [ ] **Step 2: Create CartContext**

`frontend/contexts/CartContext.tsx`:

```tsx
"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { toast } from "sonner";
import {
  addCartItem,
  createOrder,
  deleteCartItem,
  getCart,
  updateCartItem,
  type Cart,
  type CartItemCreateInput,
  type OrderCreateInput,
} from "@/lib/api";
import { isAuthenticated } from "@/lib/auth";

type CartContextValue = {
  cart: Cart | null;
  loading: boolean;
  open: boolean;
  setOpen: (open: boolean) => void;
  refresh: () => Promise<void>;
  addItem: (input: CartItemCreateInput) => Promise<void>;
  setQuantity: (itemId: number, quantity: number) => Promise<void>;
  removeItem: (itemId: number) => Promise<void>;
  checkout: (body: OrderCreateInput) => Promise<void>;
};

const CartContext = createContext<CartContextValue | null>(null);

const EMPTY: Cart = { items: [], item_count: 0, subtotal: null, checkout_ready: false };

export function CartProvider({ children }: { children: ReactNode }) {
  const [cart, setCart] = useState<Cart | null>(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);

  const refresh = useCallback(async () => {
    if (!isAuthenticated()) {
      setCart(EMPTY);
      setLoading(false);
      return;
    }
    try {
      const data = await getCart();
      setCart(data);
    } catch {
      setCart(EMPTY);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const addItem = useCallback(
    async (input: CartItemCreateInput) => {
      try {
        await addCartItem(input);
        await refresh();
        toast.success("Added to cart");
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Failed to add to cart");
        throw e;
      }
    },
    [refresh]
  );

  const setQuantity = useCallback(
    async (itemId: number, quantity: number) => {
      try {
        await updateCartItem(itemId, quantity);
        await refresh();
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Failed to update cart");
        throw e;
      }
    },
    [refresh]
  );

  const removeItem = useCallback(
    async (itemId: number) => {
      try {
        await deleteCartItem(itemId);
        await refresh();
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Failed to remove item");
        throw e;
      }
    },
    [refresh]
  );

  const checkout = useCallback(
    async (body: OrderCreateInput) => {
      try {
        await createOrder(body);
        await refresh();
        toast.success("Order placed");
        setOpen(false);
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Checkout failed");
        throw e;
      }
    },
    [refresh]
  );

  return (
    <CartContext.Provider
      value={{
        cart,
        loading,
        open,
        setOpen,
        refresh,
        addItem,
        setQuantity,
        removeItem,
        checkout,
      }}
    >
      {children}
    </CartContext.Provider>
  );
}

export function useCart(): CartContextValue {
  const ctx = useContext(CartContext);
  if (!ctx) throw new Error("useCart must be used within CartProvider");
  return ctx;
}
```

- [ ] **Step 3: Wrap chat layout**

Replace `frontend/app/(dashboard)/chat/layout.tsx` with:

```tsx
import { CartProvider } from "@/contexts/CartContext";

export default function ChatLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <CartProvider>
      <div className="h-screen flex flex-col bg-muted/40 dark:bg-background relative overflow-hidden">
        <div className="gradient-mesh" aria-hidden />
        <div className="grain" aria-hidden />
        <div className="relative z-10 h-full min-h-0">{children}</div>
      </div>
    </CartProvider>
  );
}
```

- [ ] **Step 4: Sanity check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no new errors from cart files (fix pre-existing unrelated errors only if any).

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api.ts frontend/contexts/CartContext.tsx frontend/app/\(dashboard\)/chat/layout.tsx
git commit -m "$(cat <<'EOF'
feat: add cart API client and CartProvider

EOF
)"
```

---

### Task 5: Cart Sheet + header button

**Files:**
- Create: `frontend/components/cart/CartSheet.tsx`
- Create: `frontend/components/cart/CartHeaderButton.tsx`
- Modify: `frontend/app/(dashboard)/chat/page.tsx`
- Test: manual in browser

**Interfaces:**
- Consumes: `useCart()`, shadcn `Sheet`, `Button`, `Input`, `Label`, `getProductImageUrl`
- Produces: header control that opens sheet; sheet steps `cart` | `checkout`

- [ ] **Step 1: Implement CartSheet**

Create `frontend/components/cart/CartSheet.tsx` with:

- Controlled by `open` / `setOpen` from `useCart()`
- `side`: `"left"` when `document.documentElement.dir === "rtl"`, else `"right"` (read once when opening / on mount)
- Step state: `"cart"` | `"checkout"`
- Cart step: list lines (image via `getProductImageUrl`), qty `-`/`+` calling `setQuantity`, remove calling `removeItem`, subtotal, Checkout button disabled unless `cart.checkout_ready`
- Empty: “Your cart is empty”
- Checkout step: fields recipient_name, phone, address, note; Back; Place order → `checkout(...)`
- Reset step to `"cart"` when sheet closes

Use existing UI primitives from `@/components/ui/sheet`, `button`, `input`, `label`, `textarea`.

Minimal structure sketch (implement fully in file):

```tsx
"use client";
// imports: useEffect, useState, Sheet/*, Button, Input, Label, Textarea, useCart, getProductImageUrl

export function CartSheet() {
  const { cart, open, setOpen, setQuantity, removeItem, checkout } = useCart();
  const [step, setStep] = useState<"cart" | "checkout">("cart");
  const [side, setSide] = useState<"left" | "right">("right");
  // form fields...
  useEffect(() => {
    if (typeof document !== "undefined") {
      setSide(document.documentElement.dir === "rtl" ? "left" : "right");
    }
  }, [open]);
  useEffect(() => {
    if (!open) setStep("cart");
  }, [open]);
  // render Sheet with cart list or checkout form
}
```

- [ ] **Step 2: Implement CartHeaderButton**

`frontend/components/cart/CartHeaderButton.tsx`:

```tsx
"use client";

import { ShoppingCart } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useCart } from "@/contexts/CartContext";
import { CartSheet } from "./CartSheet";

export function CartHeaderButton() {
  const { cart, setOpen } = useCart();
  const count = cart?.item_count ?? 0;

  return (
    <>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="relative h-8 w-8"
        aria-label="Open cart"
        onClick={() => setOpen(true)}
      >
        <ShoppingCart className="h-4 w-4" />
        {count > 0 && (
          <span className="absolute -top-1 -right-1 min-w-4 h-4 px-1 rounded-full bg-primary text-primary-foreground text-[10px] leading-4 text-center">
            {count > 99 ? "99+" : count}
          </span>
        )}
      </Button>
      <CartSheet />
    </>
  );
}
```

- [ ] **Step 3: Mount in chat header**

In `frontend/app/(dashboard)/chat/page.tsx`, import `CartHeaderButton` and place it in the header row (right side of title). Keep existing `SidebarTrigger` + title; add the cart button in the `justify-between` header so title stays centered-ish or left-grouped and cart on the trailing edge:

```tsx
<header className="flex h-12 shrink-0 items-center justify-between gap-2 rounded-xl border border-border/60 bg-card px-3 shadow-modern">
  <div className="flex items-center gap-2 min-w-0">
    {/* existing SidebarTrigger + tooltip */}
    <span className="text-sm font-medium text-muted-foreground truncate min-w-0">
      {currentSession?.title || "New Chat"}
    </span>
  </div>
  <CartHeaderButton />
</header>
```

- [ ] **Step 4: Manual verify**

Start backend + frontend. Open `/chat`, click cart → empty state. (Add flows come in Task 6.)

- [ ] **Step 5: Commit**

```bash
git add frontend/components/cart/CartSheet.tsx frontend/components/cart/CartHeaderButton.tsx frontend/app/\(dashboard\)/chat/page.tsx
git commit -m "$(cat <<'EOF'
feat: add cart sheet and header badge

EOF
)"
```

---

### Task 6: Add to cart from ProductSidebar + chat cards

**Files:**
- Modify: `frontend/components/chat/ProductSidebar.tsx`
- Modify: `frontend/components/chat/MessageList.tsx`
- Modify: `frontend/components/chat/ChatPanel.tsx`
- Test: manual UI

**Interfaces:**
- Consumes: `useCart().addItem`, `ProductSummary` / `ProductVariant`
- Produces: selectable variant + Add to cart in sidebar; card action that adds when no variants, otherwise selects product (opens sidebar) via existing `onProductSelect`

- [ ] **Step 1: Helper to build variant label**

Add in `ProductSidebar.tsx` (or a tiny shared helper in the same file):

```typescript
function variantLabel(v: ProductVariant): string {
  if (v.attributes && v.attributes.length > 0) {
    return v.attributes
      .map((a) => {
        const n = (a.name || "").trim();
        const val = (a.value || "").trim();
        return n && val ? `${n}: ${val}` : val || n || "";
      })
      .filter(Boolean)
      .join(" · ");
  }
  return (v.name || v.color || "").trim();
}
```

- [ ] **Step 2: Update ProductSidebar**

- Extend props: keep `product`, `onClose`; use `useCart()` inside (provider wraps chat layout).
- State: `selectedVariantIndex: number | null` — if `variants?.length`, require selection; else null means base product.
- Make variant rows clickable buttons; highlight selected.
- Footer sticky button “Add to cart”:
  - If variants exist and none selected → toast.error("Select a variant") and return
  - Else call `addItem` with snapshot (`product_id`, `subject`, `unit_price` from variant or product, `image_url` from variant.image or product.image_url, `category_name`, `variant_label`)

- [ ] **Step 3: Update ProductCards in MessageList**

- Add optional `onAddToCart?: (product: ProductSummary) => void`
- On each card, stopPropagation button “Add” that:
  - If `product.variants && product.variants.length > 0` → call `onProductSelect?.(product)` (open sidebar) instead of adding
  - Else → `onAddToCart?.(product)`
- Do not break existing select/toggle behavior for the card body click.

- [ ] **Step 4: Wire ChatPanel**

- Import `useCart`
- `handleAddToCart(product)` → `addItem({...})` without variant
- Pass `onAddToCart={handleAddToCart}` into `MessageList`
- Ensure opening sidebar still works via existing `onProductSelect` / `toggleProductSelection`

- [ ] **Step 5: Manual acceptance checklist**

1. Add product without variants from card → badge increments  
2. Product with variants from card → sidebar opens; select variant → Add to cart  
3. Change qty / remove in sheet  
4. Checkout with form → success toast, cart empty, order row in DB (`sqlite3` or API re-check cart empty)  
5. Item with null price: appears in cart; Checkout disabled  

- [ ] **Step 6: Commit**

```bash
git add frontend/components/chat/ProductSidebar.tsx frontend/components/chat/MessageList.tsx frontend/components/chat/ChatPanel.tsx
git commit -m "$(cat <<'EOF'
feat: add to cart from product sidebar and chat cards

EOF
)"
```

---

### Task 7: Final verification

**Files:** none new (run existing tests + manual)

- [ ] **Step 1: Run full backend cart/order suite**

```bash
cd backend && ./venv/bin/python -m pytest tests/test_models_smoke.py tests/test_cart.py tests/test_orders.py -v
```

Expected: all PASS

- [ ] **Step 2: Frontend typecheck**

```bash
cd frontend && npx tsc --noEmit
```

Expected: pass (or only pre-existing unrelated errors)

- [ ] **Step 3: Confirm spec coverage**

Map each success criterion in the design spec to a completed task; if anything missing, fix before claiming done.

- [ ] **Step 4: Final commit only if stray fixes remain**

```bash
git status
# if needed:
git add -A && git commit -m "$(cat <<'EOF'
fix: polish cart checkout edge cases

EOF
)"
```

---

## Plan self-review

| Spec requirement | Task |
|------------------|------|
| Server cart + JWT | 1–2 |
| Orders pending + form fields | 3 |
| Header icon + Sheet | 5 |
| Add from sidebar + variant select | 6 |
| Add from cards / variant gate | 6 |
| Null price blocks checkout | 2–3, 5 UI |
| Snapshot fields | 1–3 |
| No catalog / payment / my-orders | respected (not in plan) |
| Isolation | `test_cart_isolation` |

**Placeholder scan:** none intentional.  
**Type consistency:** `variant_label: str` default `""`; `CartOut.checkout_ready`; frontend mirrors backend field names.
