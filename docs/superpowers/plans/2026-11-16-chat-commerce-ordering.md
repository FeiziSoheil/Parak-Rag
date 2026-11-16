# Chat Commerce Ordering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a logged-in user add cart lines and place a `pending` order by chatting (text or voice), collecting recipient name, phone, and address, and creating the order only after an explicit confirm.

**Architecture:** One chat pipeline. A temperature-0 commerce detector returns action JSON. Python validates that JSON and calls the existing cart and order services. Checkout progress lives in `chat_sessions.checkout_state`. `/api/chat` and `/api/voice-chat` both go through `_run_chat_response`. The client sends `selected_products` and `sidebar_product`, then refreshes the cart when `cart_updated` is true. This is one plan: the reply, the order, and the badge are one user flow and do not ship separately.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic v2, pytest + FastAPI TestClient, existing AvalAI `ChatOpenAI` helper, Next.js 14, `CartProvider`, sonner.

**Spec:** `docs/superpowers/specs/2026-11-16-chat-commerce-ordering-design.md`

## Global Constraints

- Approach 1 only: the LLM returns commerce action JSON; the backend executes it on the existing cart and order services. Do not add a second order store. The LLM never writes the database.
- Explicit confirm. `order_confirm` creates an order only when `checkout_state.phase` is already `awaiting_confirm` at the start of that turn.
- Product pool, first non-empty source only (do not merge sources): (1) request `selected_products`, (2) request `sidebar_product`, (3) the latest assistant message in the session whose `products` JSON is non-empty. Zero candidates: explain that nothing is selected and do not add. One candidate: add it. More than one candidate: clarify and do not add, unless `product_ref.product_id` matches exactly one candidate. Hint values `first`, `this`, and color words must not choose among multiple products. A color hint may choose a variant only after one product is selected.
- Variants: if the chosen product has a non-empty `variants` list and no variant is chosen, ask and do not add. Use `sidebar_product.selected_variant_label` when its `product_id` matches. Snapshot `unit_price` and `image_url` the way `POST /api/cart/items` already does. Quantity defaults to 1.
- No catalog-wide name search. An empty pool stays empty even if the utterance names a product.
- `chat_sessions.checkout_state` is nullable TEXT JSON. `null`, blank, and invalid JSON mean idle. Shape: `phase` (`idle` | `collecting` | `awaiting_confirm`), `recipient_name`, `phone`, `address`, `note`, `next_slot` (`recipient_name` | `phone` | `address` | `note` | null).
- Required slots are `recipient_name`, `phone`, and `address`, in that order. `note` is optional and is never the blocking question.
- When `phase` is not `idle`, the detector prompt tells the model to prefer `checkout_fill`, `order_confirm`, or `order_cancel` over a catalog search. Action `none` still falls through to the existing RAG path. Image turns skip commerce.
- Chat and voice JSON add `cart_updated` (bool), `order` (`{id, total_amount, status}` or null), and `checkout_phase` (string or null). A placed order sets `cart_updated` true.
- Request fields: `selected_products` (JSON array, already used by voice) and optional `sidebar_product` (JSON object). Invalid JSON becomes `[]` or null. Do not answer 400 for bad JSON.
- Voice STT then the same `_run_chat_response`. Do not duplicate commerce logic in the voice handler.
- New orders stay `status="pending"`. Keep `/api/cart` and `/api/orders` behavior, including details `Cart is empty`, `Cart has items without price`, and `Cart item not found`.
- No payment, no confirm/cancel chips, no cart-panel redesign, no My Orders page.
- The pre-confirm reply lists line items, subtotal, recipient name, phone, address, and note when note is set.
- Empty cart on `checkout_start`, or on `checkout_fill` while still `idle`: say the cart is empty and stay `idle`.
- A null `unit_price` blocks confirm. Cancel clears the draft, sets `idle`, writes no order, and leaves cart lines in place.
- Every cart and order query filters `user_id`. A service error becomes assistant text. Do not leave a partial order.
- Commerce replies are fixed templates. Do not call a second LLM to rephrase them.
- Save the raw user utterance on the message row. Prepend `_format_product_context` only to the RAG model call.
- Commit only the files named in that task. This worktree has unrelated dirty files. Never `git add -A` or `git add .`.
- Backend tests use `cd backend && ./venv/bin/python -m pytest <target> -v`.

## File structure

| Path | Responsibility |
|------|----------------|
| `backend/app/services/checkout_state.py` | Parse, dump, and advance checkout JSON. SQLite column helper. |
| `backend/app/models/session.py` | `ChatSession.checkout_state` column. |
| `backend/app/main.py` | Call the column helper on startup. |
| `backend/app/services/commerce.py` | Cart and order functions shared by HTTP and chat. `CommerceError`. |
| `backend/app/api/cart.py` | HTTP cart routes call the service. Status codes unchanged. |
| `backend/app/api/orders.py` | HTTP checkout calls the service. Status codes unchanged. |
| `backend/app/services/commerce_actions.py` | Normalize action JSON, resolve a product, execute one action, load recent cards, detect the action. |
| `backend/app/api/chat.py` | Commerce branch inside `_run_chat_response`; request fields; response fields; voice uses that function. |
| `backend/tests/test_checkout_state.py` | State machine and column helper. |
| `backend/tests/test_commerce_service.py` | Service behavior plus the old HTTP suite still passing. |
| `backend/tests/test_product_resolve.py` | Candidate pool and variant rules. |
| `backend/tests/test_commerce_execute.py` | Cart, checkout, confirm gate, isolation. |
| `backend/tests/test_commerce_detector.py` | JSON detector with an injected completer. No network. |
| `backend/tests/test_chat_commerce.py` | `/api/chat` and `/api/voice-chat` with the detector and RAG patched. |
| `frontend/lib/commerceChat.mjs` | Sidebar snapshot and cart-refresh decision. |
| `frontend/lib/commerceChat.test.mjs` | Node test for those helpers. |
| `frontend/lib/api.ts` | Send the new fields; type the new response fields. |
| `frontend/components/chat/ProductSidebar.tsx` | Report the selected variant upward. |
| `frontend/components/chat/ChatPanel.tsx` | Send context; refresh cart; toast the order. |

---

### Task 1: Checkout state machine

**Files:**
- Create: `backend/app/services/checkout_state.py`
- Test: `backend/tests/test_checkout_state.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `empty_state() -> dict` with keys `phase`, `recipient_name`, `phone`, `address`, `note`, `next_slot`
  - `load_checkout_state(raw: str | None) -> dict`
  - `dump_checkout_state(state: dict) -> str`
  - `merge_slots(state: dict, slots: dict, *, allow_clear: bool) -> dict`
  - `advance_phase(state: dict) -> dict`
  - `begin_collecting(state: dict) -> dict`
  - `fill_slots(state: dict, slots: dict) -> dict`
  - `ready_to_confirm(state: dict) -> bool`
  - `mark_idle() -> dict`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_checkout_state.py`:

```python
from app.services.checkout_state import (
    advance_phase,
    begin_collecting,
    dump_checkout_state,
    empty_state,
    fill_slots,
    load_checkout_state,
    mark_idle,
    ready_to_confirm,
)


def test_empty_and_invalid_are_idle():
    idle = empty_state()
    assert idle == {
        "phase": "idle",
        "recipient_name": None,
        "phone": None,
        "address": None,
        "note": None,
        "next_slot": None,
    }
    assert load_checkout_state(None) == idle
    assert load_checkout_state("") == idle
    assert load_checkout_state("not-json") == idle
    assert load_checkout_state("[]") == idle


def test_load_keeps_valid_fields_and_drops_bad_phase():
    raw = dump_checkout_state(
        {
            "phase": "collecting",
            "recipient_name": "  Ada  ",
            "phone": "",
            "address": None,
            "note": " door ",
            "next_slot": "phone",
        }
    )
    loaded = load_checkout_state(raw)
    assert loaded["phase"] == "collecting"
    assert loaded["recipient_name"] == "Ada"
    assert loaded["phone"] is None
    assert loaded["note"] == "door"
    assert loaded["next_slot"] == "phone"
    assert load_checkout_state('{"phase":"nope"}')["phase"] == "idle"


def test_begin_collecting_asks_name_then_summary_when_complete():
    started = begin_collecting(empty_state())
    assert started["phase"] == "collecting"
    assert started["next_slot"] == "recipient_name"
    complete = {
        **empty_state(),
        "recipient_name": "Ada",
        "phone": "+98912",
        "address": "Tehran",
    }
    done = begin_collecting(complete)
    assert done["phase"] == "awaiting_confirm"
    assert done["next_slot"] is None
    assert ready_to_confirm(done) is True
    assert ready_to_confirm(started) is False


def test_fill_slots_walks_required_fields_and_note_is_optional():
    named = fill_slots(empty_state(), {"recipient_name": "Ada", "phone": None, "note": None})
    assert named["phase"] == "collecting"
    assert named["recipient_name"] == "Ada"
    assert named["next_slot"] == "phone"
    ready = fill_slots(
        named,
        {"phone": "+98912", "address": "Tehran", "note": "Leave at door"},
    )
    assert ready["phase"] == "awaiting_confirm"
    assert ready["note"] == "Leave at door"
    assert ready["next_slot"] is None


def test_clear_is_ignored_until_awaiting_confirm():
    collecting = fill_slots(empty_state(), {"recipient_name": "Ada"})
    kept = fill_slots(collecting, {"recipient_name": ""})
    assert kept["recipient_name"] == "Ada"
    waiting = fill_slots(collecting, {"phone": "+1", "address": "Tehran"})
    cleared = fill_slots(waiting, {"phone": ""})
    assert cleared["phase"] == "collecting"
    assert cleared["phone"] is None
    assert cleared["next_slot"] == "phone"
    assert ready_to_confirm(cleared) is False


def test_mark_idle_drops_draft():
    waiting = fill_slots(
        empty_state(),
        {"recipient_name": "Ada", "phone": "+1", "address": "Tehran"},
    )
    assert mark_idle() == empty_state()
    assert waiting["recipient_name"] == "Ada"


def test_advance_phase_never_blocks_on_note():
    state = advance_phase(
        {
            **empty_state(),
            "recipient_name": "Ada",
            "phone": "+1",
            "address": "Tehran",
            "note": None,
        }
    )
    assert state["phase"] == "awaiting_confirm"
    assert state["next_slot"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_checkout_state.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.checkout_state'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/services/checkout_state.py`:

```python
import json

REQUIRED_SLOTS = ("recipient_name", "phone", "address")
OPTIONAL_SLOTS = ("note",)
ALL_SLOTS = REQUIRED_SLOTS + OPTIONAL_SLOTS
PHASES = ("idle", "collecting", "awaiting_confirm")
NEXT_SLOTS = REQUIRED_SLOTS + ("note",)


def empty_state() -> dict:
    return {
        "phase": "idle",
        "recipient_name": None,
        "phone": None,
        "address": None,
        "note": None,
        "next_slot": None,
    }


def _clean_stored(value) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    return value or None


def load_checkout_state(raw: str | None) -> dict:
    state = empty_state()
    if raw is None or not str(raw).strip():
        return state
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return state
    if not isinstance(data, dict):
        return state
    phase = data.get("phase")
    state["phase"] = phase if phase in PHASES else "idle"
    for key in ALL_SLOTS:
        state[key] = _clean_stored(data.get(key))
    next_slot = data.get("next_slot")
    state["next_slot"] = next_slot if next_slot in NEXT_SLOTS else None
    return state


def dump_checkout_state(state: dict) -> str:
    payload = empty_state()
    payload.update({key: state.get(key) for key in payload})
    return json.dumps(payload, ensure_ascii=False)


def merge_slots(state: dict, slots: dict, *, allow_clear: bool) -> dict:
    out = dict(state)
    for key in ALL_SLOTS:
        if key not in slots or slots[key] is None:
            continue
        raw = slots[key]
        cleaned = raw.strip() if isinstance(raw, str) else str(raw).strip()
        if cleaned == "":
            if allow_clear:
                out[key] = None
            continue
        out[key] = cleaned
    return out


def advance_phase(state: dict) -> dict:
    out = dict(state)
    missing = next((key for key in REQUIRED_SLOTS if not out.get(key)), None)
    if missing:
        out["phase"] = "collecting"
        out["next_slot"] = missing
    else:
        out["phase"] = "awaiting_confirm"
        out["next_slot"] = None
    return out


def begin_collecting(state: dict) -> dict:
    return advance_phase(dict(state))


def fill_slots(state: dict, slots: dict) -> dict:
    merged = merge_slots(state, slots, allow_clear=state.get("phase") == "awaiting_confirm")
    return advance_phase(merged)


def ready_to_confirm(state: dict) -> bool:
    return state.get("phase") == "awaiting_confirm" and all(state.get(key) for key in REQUIRED_SLOTS)


def mark_idle() -> dict:
    return empty_state()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_checkout_state.py -v`

Expected: PASS (`7 passed`)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/checkout_state.py backend/tests/test_checkout_state.py
git commit -m "$(cat <<'EOF'
feat: add checkout state transitions

EOF
)"
```

---

### Task 2: Persist checkout_state on chat sessions

**Files:**
- Modify: `backend/app/services/checkout_state.py`
- Modify: `backend/app/models/session.py`
- Modify: `backend/app/main.py` (lifespan ensures, next to `_ensure_user_email_columns`)
- Test: `backend/tests/test_checkout_state.py`

**Interfaces:**
- Consumes: `dump_checkout_state`, `load_checkout_state`, `empty_state` from Task 1
- Produces: `ChatSession.checkout_state` (`Text`, nullable); `ensure_checkout_state_column(connection) -> None`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_checkout_state.py`:

```python
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.models.session import ChatSession
from app.services.checkout_state import (
    dump_checkout_state,
    empty_state,
    ensure_checkout_state_column,
    load_checkout_state,
)


def test_ensure_checkout_state_column_adds_and_is_idempotent():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE chat_sessions ("
                "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, title VARCHAR(512))"
            )
        )
    with engine.connect() as conn:
        ensure_checkout_state_column(conn)
        cols = [row[1] for row in conn.execute(text("PRAGMA table_info(chat_sessions)"))]
        assert "checkout_state" in cols
        ensure_checkout_state_column(conn)
        cols_again = [row[1] for row in conn.execute(text("PRAGMA table_info(chat_sessions)"))]
        assert cols_again.count("checkout_state") == 1


def test_chat_session_persists_checkout_state(db_session, user_a):
    raw = dump_checkout_state(
        {
            **empty_state(),
            "phase": "collecting",
            "recipient_name": "Ada",
            "next_slot": "phone",
        }
    )
    row = ChatSession(user_id=user_a.id, title="New Chat", checkout_state=raw)
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    loaded = load_checkout_state(row.checkout_state)
    assert loaded["phase"] == "collecting"
    assert loaded["recipient_name"] == "Ada"
    assert loaded["next_slot"] == "phone"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_checkout_state.py::test_ensure_checkout_state_column_adds_and_is_idempotent tests/test_checkout_state.py::test_chat_session_persists_checkout_state -v`

Expected: FAIL. `ensure_checkout_state_column` is missing, and `ChatSession()` does not accept `checkout_state`.

- [ ] **Step 3: Write minimal implementation**

Append to `backend/app/services/checkout_state.py`:

```python
from sqlalchemy import text


def ensure_checkout_state_column(connection) -> None:
    rows = connection.execute(text("PRAGMA table_info(chat_sessions)"))
    cols = [row[1] for row in rows]
    if "checkout_state" not in cols:
        connection.execute(text("ALTER TABLE chat_sessions ADD COLUMN checkout_state TEXT"))
        connection.commit()
```

In `backend/app/models/session.py`, change the SQLAlchemy import to include `Text` and add the column after `pinned`:

```python
from sqlalchemy import Boolean, Column, Integer, String, DateTime, ForeignKey, Text
```

```python
    pinned = Column(Boolean, default=False, nullable=False)
    checkout_state = Column(Text, nullable=True)
```

In `backend/app/main.py`, import the helper and call it from lifespan after the existing ensure calls. Do not change CORS or routers.

```python
from app.services.checkout_state import ensure_checkout_state_column
```

```python
def _ensure_checkout_state_column():
    """Add chat_sessions.checkout_state if missing (existing SQLite files)."""
    if "sqlite" not in str(engine.url):
        return
    with engine.connect() as conn:
        ensure_checkout_state_column(conn)
```

Inside `lifespan`, immediately after `_ensure_user_email_columns()`:

```python
    _ensure_products_column()
    _ensure_user_email_columns()
    _ensure_checkout_state_column()
```

Do not put `checkout_state` on `SessionResponse`. The session list API stays as it is.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_checkout_state.py tests/test_models_smoke.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/checkout_state.py backend/app/models/session.py backend/app/main.py backend/tests/test_checkout_state.py
git commit -m "$(cat <<'EOF'
feat: store checkout state on chat sessions

EOF
)"
```

---

### Task 3: Share cart and order services with chat

**Files:**
- Create: `backend/app/services/commerce.py`
- Modify: `backend/app/api/cart.py`
- Modify: `backend/app/api/orders.py`
- Test: `backend/tests/test_commerce_service.py`
- Test (unchanged assertions): `backend/tests/test_cart.py`, `backend/tests/test_orders.py`

**Interfaces:**
- Consumes: `CartItemCreate`, `CartOut`, `OrderCreate`, `CartItem`, `Order`, `OrderItem`
- Produces:
  - `class CommerceError(Exception)` with `.detail: str` and `.status_code: int`
  - `serialize_cart(items: list[CartItem]) -> CartOut`
  - `get_cart_for_user(db, user_id: int) -> CartOut`
  - `add_cart_item(db, user_id: int, body: CartItemCreate) -> CartItem`
  - `update_cart_item(db, user_id: int, item_id: int, quantity: int) -> CartItem`
  - `delete_cart_item(db, user_id: int, item_id: int) -> None`
  - `create_order_from_cart(db, user_id: int, body: OrderCreate) -> Order`
  - HTTP details stay exactly `Cart is empty`, `Cart has items without price`, `Cart item not found`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_commerce_service.py`:

```python
import pytest

from app.schemas.cart import CartItemCreate
from app.schemas.order import OrderCreate
from app.services.commerce import (
    CommerceError,
    add_cart_item,
    create_order_from_cart,
    get_cart_for_user,
    update_cart_item,
)

SAMPLE = {
    "product_id": 101,
    "subject": "Blue Mug",
    "unit_price": 12.5,
    "image_url": "https://example.com/mug.jpg",
    "category_name": "Home",
    "variant_label": "",
    "quantity": 1,
}

CHECKOUT = {
    "recipient_name": "Alice",
    "phone": "+98912",
    "address": "Tehran",
    "note": "Leave at door",
}


def test_add_increments_same_variant(db_session, user_a):
    body = CartItemCreate(**SAMPLE)
    first = add_cart_item(db_session, user_a.id, body)
    second = add_cart_item(db_session, user_a.id, body)
    assert first.id == second.id
    assert second.quantity == 2
    cart = get_cart_for_user(db_session, user_a.id)
    assert cart.item_count == 2
    assert cart.subtotal == 25.0
    assert cart.checkout_ready is True


def test_update_other_user_is_not_found(db_session, user_a, user_b):
    item = add_cart_item(db_session, user_a.id, CartItemCreate(**SAMPLE))
    with pytest.raises(CommerceError) as caught:
        update_cart_item(db_session, user_b.id, item.id, 4)
    assert caught.value.status_code == 404
    assert caught.value.detail == "Cart item not found"
    assert get_cart_for_user(db_session, user_a.id).items[0].quantity == 1


def test_create_order_snapshots_and_clears_cart(db_session, user_a):
    add_cart_item(db_session, user_a.id, CartItemCreate(**SAMPLE))
    order = create_order_from_cart(db_session, user_a.id, OrderCreate(**CHECKOUT))
    assert order.status == "pending"
    assert order.total_amount == 12.5
    assert order.items[0].subject == "Blue Mug"
    assert get_cart_for_user(db_session, user_a.id).items == []


def test_create_order_empty_and_null_price_use_http_details(db_session, user_a):
    with pytest.raises(CommerceError) as empty:
        create_order_from_cart(db_session, user_a.id, OrderCreate(**CHECKOUT))
    assert empty.value.status_code == 400
    assert empty.value.detail == "Cart is empty"

    add_cart_item(db_session, user_a.id, CartItemCreate(**{**SAMPLE, "unit_price": None}))
    with pytest.raises(CommerceError) as missing:
        create_order_from_cart(db_session, user_a.id, OrderCreate(**CHECKOUT))
    assert missing.value.status_code == 400
    assert missing.value.detail == "Cart has items without price"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_commerce_service.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.commerce'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/services/commerce.py` by moving the current router bodies. Keep the upsert, the null-price check, the snapshot copy, and the cart delete inside the same commit as the order.

```python
from sqlalchemy.orm import Session

from app.models.cart import CartItem
from app.models.order import Order, OrderItem
from app.schemas.cart import CartItemCreate, CartItemOut, CartOut
from app.schemas.order import OrderCreate


class CommerceError(Exception):
    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


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


def get_cart_for_user(db: Session, user_id: int) -> CartOut:
    items = db.query(CartItem).filter(CartItem.user_id == user_id).order_by(CartItem.id).all()
    return serialize_cart(items)


def add_cart_item(db: Session, user_id: int, body: CartItemCreate) -> CartItem:
    if body.quantity < 1:
        raise CommerceError("quantity must be >= 1", 400)
    variant = _normalize_variant(body.variant_label)
    existing = (
        db.query(CartItem)
        .filter(
            CartItem.user_id == user_id,
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
        user_id=user_id,
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


def update_cart_item(db: Session, user_id: int, item_id: int, quantity: int) -> CartItem:
    if quantity < 1:
        raise CommerceError("quantity must be >= 1", 400)
    item = (
        db.query(CartItem)
        .filter(CartItem.id == item_id, CartItem.user_id == user_id)
        .first()
    )
    if not item:
        raise CommerceError("Cart item not found", 404)
    item.quantity = quantity
    db.commit()
    db.refresh(item)
    return item


def delete_cart_item(db: Session, user_id: int, item_id: int) -> None:
    item = (
        db.query(CartItem)
        .filter(CartItem.id == item_id, CartItem.user_id == user_id)
        .first()
    )
    if not item:
        raise CommerceError("Cart item not found", 404)
    db.delete(item)
    db.commit()


def create_order_from_cart(db: Session, user_id: int, body: OrderCreate) -> Order:
    items = db.query(CartItem).filter(CartItem.user_id == user_id).all()
    if not items:
        raise CommerceError("Cart is empty", 400)
    if any(i.unit_price is None for i in items):
        raise CommerceError("Cart has items without price", 400)

    total = float(sum((i.unit_price or 0) * i.quantity for i in items))
    order = Order(
        user_id=user_id,
        status="pending",
        recipient_name=body.recipient_name.strip(),
        phone=body.phone.strip(),
        address=body.address.strip(),
        note=(body.note.strip() if body.note else None),
        total_amount=total,
    )
    db.add(order)
    db.flush()
    for item in items:
        db.add(
            OrderItem(
                order_id=order.id,
                product_id=item.product_id,
                subject=item.subject,
                unit_price=float(item.unit_price),
                image_url=item.image_url,
                category_name=item.category_name or "",
                variant_label=item.variant_label or "",
                quantity=item.quantity,
            )
        )
        db.delete(item)
    db.commit()
    db.refresh(order)
    _ = order.items
    return order
```

Replace `backend/app/api/cart.py` with thin routes. FastAPI still validates bodies, so quantity `0` on PATCH stays 422.

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.cart import CartItemCreate, CartItemUpdate, CartItemOut, CartOut
from app.services.commerce import (
    CommerceError,
    add_cart_item as add_cart_item_service,
    delete_cart_item as delete_cart_item_service,
    get_cart_for_user,
    update_cart_item as update_cart_item_service,
)

router = APIRouter()


def _raise(err: CommerceError) -> None:
    raise HTTPException(status_code=err.status_code, detail=err.detail)


@router.get("/cart", response_model=CartOut)
def get_cart(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_cart_for_user(db, current_user.id)


@router.post("/cart/items", response_model=CartItemOut)
def add_cart_item(
    body: CartItemCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return add_cart_item_service(db, current_user.id, body)
    except CommerceError as err:
        _raise(err)


@router.patch("/cart/items/{item_id}", response_model=CartItemOut)
def update_cart_item(
    item_id: int,
    body: CartItemUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return update_cart_item_service(db, current_user.id, item_id, body.quantity)
    except CommerceError as err:
        _raise(err)


@router.delete("/cart/items/{item_id}", status_code=204)
def delete_cart_item(
    item_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        delete_cart_item_service(db, current_user.id, item_id)
    except CommerceError as err:
        _raise(err)
    return None
```

Replace `backend/app/api/orders.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.order import OrderCreate, OrderOut
from app.services.commerce import CommerceError, create_order_from_cart

router = APIRouter()


@router.post("/orders", response_model=OrderOut)
def create_order(
    body: OrderCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return create_order_from_cart(db, current_user.id, body)
    except CommerceError as err:
        raise HTTPException(status_code=err.status_code, detail=err.detail)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_commerce_service.py tests/test_cart.py tests/test_orders.py -v`

Expected: PASS. Existing cart and order HTTP tests stay green, including isolation, null price, and quantity `0` rejected with 422 or 400.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/commerce.py backend/app/api/cart.py backend/app/api/orders.py backend/tests/test_commerce_service.py
git commit -m "$(cat <<'EOF'
refactor: share cart and order services with chat

EOF
)"
```

---

### Task 4: Resolve a product from chat context

**Files:**
- Create: `backend/app/services/commerce_actions.py`
- Test: `backend/tests/test_product_resolve.py`

**Interfaces:**
- Consumes: nothing from Tasks 1–3
- Produces:
  - `@dataclass ResolveProduct` with `status: str` (`selected` | `none` | `clarify` | `need_variant`), `product: dict | None`, `candidates: list[dict]`, `variant_options: list[str]`
  - `resolve_product_for_cart(attached: list[dict], sidebar: dict | None, recent: list[dict], product_ref: dict | None) -> ResolveProduct`
  - Selected `product` keys: `product_id: int`, `subject: str`, `unit_price: float | None`, `image_url: str | None`, `category_name: str`, `variant_label: str`
  - Input products may use `price` or `unit_price`. Variant objects use `attributes[{name, value}]`, optional `name` / `color`, `price`, and `image`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_product_resolve.py`:

```python
from app.services.commerce_actions import resolve_product_for_cart

MUG = {
    "product_id": 101,
    "subject": "Blue Mug",
    "price": 12.5,
    "image_url": "https://example.com/mug.jpg",
    "category_name": "Home",
    "variants": [],
}
SHIRT = {
    "product_id": 202,
    "subject": "Shirt",
    "price": 20.0,
    "image_url": None,
    "category_name": "Clothes",
    "variants": [
        {
            "price": 22.0,
            "image": "https://example.com/blue.jpg",
            "attributes": [{"name": "Color", "value": "Blue"}],
        },
        {
            "price": 23.0,
            "image": "https://example.com/red.jpg",
            "attributes": [{"name": "Color", "value": "Red"}],
        },
    ],
}
CUP = {
    "product_id": 303,
    "subject": "Cup",
    "price": 5.0,
    "image_url": None,
    "category_name": "Home",
    "variants": [],
}


def test_no_candidates():
    resolved = resolve_product_for_cart([], None, [], {"hint": None, "product_id": None})
    assert resolved.status == "none"
    assert resolved.product is None


def test_single_attached_product_snapshots_price():
    resolved = resolve_product_for_cart([MUG], None, [CUP], None)
    assert resolved.status == "selected"
    assert resolved.product["product_id"] == 101
    assert resolved.product["unit_price"] == 12.5
    assert resolved.product["image_url"] == "https://example.com/mug.jpg"
    assert resolved.product["variant_label"] == ""


def test_attached_beats_sidebar_and_recent():
    sidebar = {**CUP, "selected_variant_label": None}
    resolved = resolve_product_for_cart([MUG], sidebar, [SHIRT], {"hint": "first", "product_id": None})
    assert resolved.status == "selected"
    assert resolved.product["product_id"] == 101


def test_sidebar_used_when_nothing_attached_and_variant_is_selected():
    sidebar = {
        **SHIRT,
        "price": 22.0,
        "image_url": "https://example.com/blue.jpg",
        "selected_variant_label": "Color: Blue",
    }
    resolved = resolve_product_for_cart([], sidebar, [MUG, CUP], {"hint": "this", "product_id": None})
    assert resolved.status == "selected"
    assert resolved.product["product_id"] == 202
    assert resolved.product["variant_label"] == "Color: Blue"
    assert resolved.product["unit_price"] == 22.0
    assert resolved.product["image_url"] == "https://example.com/blue.jpg"


def test_recent_cards_used_only_when_attached_and_sidebar_missing():
    resolved = resolve_product_for_cart([], None, [MUG], None)
    assert resolved.status == "selected"
    assert resolved.product["product_id"] == 101


def test_multiple_products_clarify_even_for_first_or_blue():
    for hint in ("first", "this", "blue", None):
        resolved = resolve_product_for_cart([], None, [MUG, CUP], {"hint": hint, "product_id": None})
        assert resolved.status == "clarify"
        assert resolved.product is None
        assert [c["product_id"] for c in resolved.candidates] == [101, 303]


def test_product_id_picks_one_of_many():
    resolved = resolve_product_for_cart(
        [],
        None,
        [MUG, CUP],
        {"hint": None, "product_id": 303, "variant_label": None},
    )
    assert resolved.status == "selected"
    assert resolved.product["product_id"] == 303


def test_variants_require_a_choice():
    resolved = resolve_product_for_cart([SHIRT], None, [], None)
    assert resolved.status == "need_variant"
    assert resolved.product is None
    assert resolved.variant_options == ["Color: Blue", "Color: Red"]


def test_hint_selects_one_variant_of_the_one_product():
    resolved = resolve_product_for_cart(
        [SHIRT],
        None,
        [],
        {"hint": "blue", "product_id": None, "variant_label": None},
    )
    assert resolved.status == "selected"
    assert resolved.product["variant_label"] == "Color: Blue"
    assert resolved.product["unit_price"] == 22.0
    assert resolved.product["image_url"] == "https://example.com/blue.jpg"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_product_resolve.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.commerce_actions'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/services/commerce_actions.py`:

```python
from dataclasses import dataclass, field


@dataclass
class ResolveProduct:
    status: str
    product: dict | None = None
    candidates: list[dict] = field(default_factory=list)
    variant_options: list[str] = field(default_factory=list)


def variant_label_of(variant: dict) -> str:
    attrs = variant.get("attributes") or []
    parts: list[str] = []
    for attr in attrs:
        if not isinstance(attr, dict):
            continue
        name = (attr.get("name") or "").strip()
        value = (attr.get("value") or "").strip()
        if name and value:
            parts.append(f"{name}: {value}")
        elif value or name:
            parts.append(value or name)
    if parts:
        return " · ".join(parts)
    return (variant.get("name") or variant.get("color") or "").strip()


def _number(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _as_candidate(raw: dict) -> dict | None:
    if not isinstance(raw, dict) or raw.get("product_id") is None:
        return None
    try:
        product_id = int(raw["product_id"])
    except (TypeError, ValueError):
        return None
    price = raw.get("unit_price", raw.get("price"))
    variants = raw.get("variants") if isinstance(raw.get("variants"), list) else []
    label = raw.get("selected_variant_label")
    if isinstance(label, str):
        label = label.strip() or None
    else:
        label = None
    return {
        "product_id": product_id,
        "subject": raw.get("subject") or "",
        "price": _number(price),
        "image_url": raw.get("image_url"),
        "category_name": raw.get("category_name") or "",
        "variants": [v for v in variants if isinstance(v, dict)],
        "selected_variant_label": label,
    }


def _pool(attached: list[dict], sidebar: dict | None, recent: list[dict]) -> list[dict]:
    attached_cards = [c for c in (_as_candidate(p) for p in attached) if c]
    if attached_cards:
        return attached_cards
    side = _as_candidate(sidebar) if isinstance(sidebar, dict) else None
    if side:
        return [side]
    return [c for c in (_as_candidate(p) for p in recent) if c]


def _match_variants(variants: list[dict], needle: str) -> list[dict]:
    text = needle.strip().lower()
    if not text:
        return []
    hits = []
    for variant in variants:
        label = variant_label_of(variant).lower()
        if text in label or (label and label in text):
            hits.append(variant)
    return hits


def _snapshot(chosen: dict, label: str, price, image) -> dict:
    return {
        "product_id": chosen["product_id"],
        "subject": chosen["subject"],
        "unit_price": _number(price),
        "image_url": image,
        "category_name": chosen["category_name"],
        "variant_label": label,
    }


def resolve_product_for_cart(
    attached: list[dict],
    sidebar: dict | None,
    recent: list[dict],
    product_ref: dict | None,
) -> ResolveProduct:
    pool = _pool(attached or [], sidebar, recent or [])
    if not pool:
        return ResolveProduct(status="none")
    ref = product_ref or {}
    chosen = None
    product_id = ref.get("product_id")
    if product_id is not None:
        try:
            product_id = int(product_id)
        except (TypeError, ValueError):
            product_id = None
    if product_id is not None:
        hits = [item for item in pool if item["product_id"] == product_id]
        if len(hits) == 1:
            chosen = hits[0]
        elif len(pool) > 1:
            return ResolveProduct(status="clarify", candidates=pool)
    if chosen is None and len(pool) > 1:
        return ResolveProduct(status="clarify", candidates=pool)
    if chosen is None:
        chosen = pool[0]

    options = [variant_label_of(v) for v in chosen["variants"]]
    options = [label for label in options if label]
    label = None
    price = chosen["price"]
    image = chosen["image_url"]
    side = _as_candidate(sidebar) if isinstance(sidebar, dict) else None
    if side and side["product_id"] == chosen["product_id"] and side["selected_variant_label"]:
        label = side["selected_variant_label"]
        if side["price"] is not None:
            price = side["price"]
        if side["image_url"]:
            image = side["image_url"]

    ref_label = ref.get("variant_label")
    if isinstance(ref_label, str):
        ref_label = ref_label.strip()
    else:
        ref_label = ""
    hint = ref.get("hint")
    hint_text = hint.strip() if isinstance(hint, str) else ""
    if label is None and ref_label:
        matched = _match_variants(chosen["variants"], ref_label)
        if len(matched) == 1:
            variant = matched[0]
            label = variant_label_of(variant)
            if variant.get("price") is not None:
                price = variant.get("price")
            if variant.get("image"):
                image = variant.get("image")
        elif chosen["variants"]:
            return ResolveProduct(status="need_variant", candidates=[chosen], variant_options=options)
        else:
            label = ref_label
    if label is None and hint_text and hint_text not in ("first", "this"):
        matched = _match_variants(chosen["variants"], hint_text)
        if len(matched) == 1:
            variant = matched[0]
            label = variant_label_of(variant)
            if variant.get("price") is not None:
                price = variant.get("price")
            if variant.get("image"):
                image = variant.get("image")
        elif len(matched) > 1:
            return ResolveProduct(status="need_variant", candidates=[chosen], variant_options=options)
    if label is None:
        if chosen["variants"]:
            return ResolveProduct(status="need_variant", candidates=[chosen], variant_options=options)
        label = ""
    return ResolveProduct(status="selected", product=_snapshot(chosen, label, price, image))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_product_resolve.py -v`

Expected: PASS (`9 passed`)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/commerce_actions.py backend/tests/test_product_resolve.py
git commit -m "$(cat <<'EOF'
feat: resolve chat product references for the cart

EOF
)"
```

---

### Task 5: Execute commerce actions

**Files:**
- Modify: `backend/app/services/commerce_actions.py`
- Test: `backend/tests/test_commerce_execute.py`

**Interfaces:**
- Consumes:
  - `empty_state`, `load_checkout_state`, `dump_checkout_state`, `begin_collecting`, `fill_slots`, `ready_to_confirm`, `mark_idle`
  - `get_cart_for_user`, `add_cart_item`, `update_cart_item`, `delete_cart_item`, `create_order_from_cart`, `CommerceError`
  - `resolve_product_for_cart` → `ResolveProduct`
  - `CartItemCreate`, `OrderCreate`, `ChatSession`, `Message`, `Order`
- Produces:
  - `normalize_commerce_action(data: dict | None) -> dict` with keys `action`, `quantity: int`, `remove: bool`, `product_ref` (`hint`, `product_id`, `variant_label`), `slots` (`recipient_name`, `phone`, `address`, `note`), `confirm: bool`, `cancel: bool`
  - Allowed `action` values: `cart_add`, `cart_view`, `cart_update`, `checkout_start`, `checkout_fill`, `order_confirm`, `order_cancel`, `clarify_product`, `none`
  - `load_recent_product_cards(db, session_id: int) -> list[dict]`
  - `@dataclass CommerceTurn` with `message: str`, `cart_updated: bool`, `order: dict | None`, `checkout_phase: str`
  - `execute_commerce_action(db, user_id: int, session, action: dict, *, attached_products: list[dict], sidebar_product: dict | None, recent_products: list[dict] | None = None) -> CommerceTurn`
  - `order` on success is `{"id": int, "total_amount": float, "status": "pending"}`

Locked reply strings:

- `Your cart is empty. Add a product before checkout.`
- `I can place the order only after you review the summary and reply yes.`
- `I can't place the order yet because a cart item has no price.`
- `I don't know which product to add. Open a product in the sidebar or pick one of the cards I showed.`
- `Which product should I add?`
- `Which variant of {subject} should I add?`
- `Checkout cancelled. Your cart is unchanged.`
- `Who should receive this order? Please send the recipient's full name.`
- `What phone number should we use for delivery?`
- `What is the delivery address?`
- `I couldn't find that item in your cart.`
- `Which cart item should I change?`
- Summary starts with `Please confirm this order:` and includes `Subtotal:`, `Recipient:`, `Phone:`, `Address:`, plus `Note:` only when note is set
- Add line: `Added {quantity} × {subject}` and ` ({variant_label})` when the label is non-empty, then ` to your cart.`
- Success line: `Order #{id} placed. Status: pending. Total: ${total:.2f}.`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_commerce_execute.py`:

```python
import json

from app.models.cart import CartItem
from app.models.message import Message
from app.models.order import Order
from app.models.session import ChatSession
from app.services.checkout_state import load_checkout_state
from app.services.commerce import CommerceError
from app.services.commerce_actions import (
    execute_commerce_action,
    load_recent_product_cards,
    normalize_commerce_action,
)

MUG = {
    "product_id": 101,
    "subject": "Blue Mug",
    "price": 12.5,
    "image_url": "https://example.com/mug.jpg",
    "category_name": "Home",
    "variants": [],
}
CUP = {
    "product_id": 303,
    "subject": "Cup",
    "price": 5.0,
    "image_url": None,
    "category_name": "Home",
    "variants": [],
}
SHIRT = {
    "product_id": 202,
    "subject": "Shirt",
    "price": 20.0,
    "image_url": None,
    "category_name": "Clothes",
    "variants": [
        {"price": 22.0, "image": "https://example.com/blue.jpg", "attributes": [{"name": "Color", "value": "Blue"}]},
        {"price": 23.0, "image": "https://example.com/red.jpg", "attributes": [{"name": "Color", "value": "Red"}]},
    ],
}


def _session(db, user) -> ChatSession:
    row = ChatSession(user_id=user.id, title="New Chat")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _run(db, user, session, action, **kwargs):
    return execute_commerce_action(
        db,
        user.id,
        session,
        action,
        attached_products=kwargs.get("attached", []),
        sidebar_product=kwargs.get("sidebar"),
        recent_products=kwargs.get("recent"),
    )


def test_normalize_defaults_and_confirm_cancel_flags():
    none = normalize_commerce_action(None)
    assert none["action"] == "none"
    assert none["quantity"] == 1
    assert none["remove"] is False
    confirmed = normalize_commerce_action({"action": "none", "confirm": True, "slots": {"phone": " +1 "}})
    assert confirmed["action"] == "order_confirm"
    assert confirmed["slots"]["phone"] == "+1"
    cancelled = normalize_commerce_action({"action": "none", "confirm": True, "cancel": True})
    assert cancelled["action"] == "order_cancel"
    assert normalize_commerce_action({"action": "cart_update", "quantity": 0})["remove"] is True
    assert normalize_commerce_action({"action": "fly"})["action"] == "none"


def test_recent_cards_skip_assistant_turns_without_products(db_session, user_a):
    session = _session(db_session, user_a)
    db_session.add(Message(session_id=session.id, role="assistant", content="cards", products=json.dumps([MUG, CUP])))
    db_session.add(Message(session_id=session.id, role="assistant", content="which one?", products=None))
    db_session.commit()
    cards = load_recent_product_cards(db_session, session.id)
    assert [c["product_id"] for c in cards] == [101, 303]


def test_add_one_updates_only_that_user(db_session, user_a, user_b):
    session_a = _session(db_session, user_a)
    session_b = _session(db_session, user_b)
    turn = _run(db_session, user_a, session_a, {"action": "cart_add", "quantity": 2}, attached=[MUG])
    assert turn.cart_updated is True
    assert turn.order is None
    assert "Added 2 × Blue Mug to your cart." in turn.message
    assert db_session.query(CartItem).filter(CartItem.user_id == user_a.id).one().quantity == 2
    other = _run(db_session, user_b, session_b, {"action": "cart_view"})
    assert "Your cart is empty." in other.message
    assert db_session.query(CartItem).filter(CartItem.user_id == user_b.id).count() == 0


def test_ambiguous_add_and_missing_variant_do_not_mutate(db_session, user_a):
    session = _session(db_session, user_a)
    vague = _run(
        db_session,
        user_a,
        session,
        {"action": "cart_add", "product_ref": {"hint": "first"}},
        recent=[MUG, CUP],
    )
    assert vague.cart_updated is False
    assert "Which product should I add?" in vague.message
    assert "Blue Mug" in vague.message and "Cup" in vague.message
    variant = _run(db_session, user_a, session, {"action": "cart_add"}, attached=[SHIRT])
    assert "Which variant of Shirt should I add?" in variant.message
    assert db_session.query(CartItem).filter(CartItem.user_id == user_a.id).count() == 0
    missing = _run(db_session, user_a, session, {"action": "cart_add"})
    assert missing.message == "I don't know which product to add. Open a product in the sidebar or pick one of the cards I showed."


def test_sidebar_variant_add(db_session, user_a):
    session = _session(db_session, user_a)
    sidebar = {
        **SHIRT,
        "price": 22.0,
        "image_url": "https://example.com/blue.jpg",
        "selected_variant_label": "Color: Blue",
    }
    turn = _run(db_session, user_a, session, {"action": "cart_add"}, sidebar=sidebar)
    assert "Added 1 × Shirt (Color: Blue) to your cart." in turn.message
    item = db_session.query(CartItem).filter(CartItem.user_id == user_a.id).one()
    assert item.variant_label == "Color: Blue"
    assert item.unit_price == 22.0
    assert item.image_url == "https://example.com/blue.jpg"


def test_update_quantity_remove_and_unknown_item(db_session, user_a):
    session = _session(db_session, user_a)
    _run(db_session, user_a, session, {"action": "cart_add"}, attached=[MUG])
    _run(db_session, user_a, session, {"action": "cart_add"}, attached=[CUP])
    ambiguous = _run(db_session, user_a, session, {"action": "cart_update", "quantity": 3})
    assert "Which cart item should I change?" in ambiguous.message
    updated = _run(
        db_session,
        user_a,
        session,
        {"action": "cart_update", "quantity": 3, "product_ref": {"product_id": 101}},
    )
    assert updated.cart_updated is True
    mug = db_session.query(CartItem).filter(CartItem.user_id == user_a.id, CartItem.product_id == 101).one()
    assert mug.quantity == 3
    removed = _run(
        db_session,
        user_a,
        session,
        {"action": "cart_update", "remove": True, "product_ref": {"product_id": 303}},
    )
    assert removed.cart_updated is True
    assert db_session.query(CartItem).filter(CartItem.user_id == user_a.id, CartItem.product_id == 303).count() == 0
    missing = _run(
        db_session,
        user_a,
        session,
        {"action": "cart_update", "quantity": 1, "product_ref": {"product_id": 999}},
    )
    assert missing.message == "I couldn't find that item in your cart."


def _collect_ready(db, user, session):
    _run(db, user, session, {"action": "cart_add"}, attached=[MUG])
    _run(db, user, session, {"action": "checkout_start"})
    _run(db, user, session, {"action": "checkout_fill", "slots": {"recipient_name": "Ada"}})
    return _run(
        db,
        user,
        session,
        {"action": "checkout_fill", "slots": {"phone": "+98912", "address": "Tehran", "note": "Leave at door"}},
    )


def test_checkout_collects_summary_and_blocks_early_or_null_price(db_session, user_a):
    session = _session(db_session, user_a)
    empty = _run(db_session, user_a, session, {"action": "checkout_start"})
    assert empty.message == "Your cart is empty. Add a product before checkout."
    assert load_checkout_state(session.checkout_state)["phase"] == "idle"

    _run(db_session, user_a, session, {"action": "cart_add"}, attached=[MUG])
    started = _run(db_session, user_a, session, {"action": "checkout_start"})
    assert started.checkout_phase == "collecting"
    assert started.message == "Who should receive this order? Please send the recipient's full name."

    too_soon = _run(db_session, user_a, session, {"action": "order_confirm"})
    assert too_soon.order is None
    assert too_soon.message == "I can place the order only after you review the summary and reply yes."
    assert db_session.query(Order).count() == 0

    named = _run(
        db_session,
        user_a,
        session,
        {"action": "checkout_fill", "slots": {"recipient_name": "Ada"}},
    )
    assert named.message == "What phone number should we use for delivery?"
    summary = _run(
        db_session,
        user_a,
        session,
        {
            "action": "checkout_fill",
            "slots": {"phone": "+98912", "address": "Tehran", "note": "Leave at door"},
        },
    )
    assert summary.checkout_phase == "awaiting_confirm"
    assert summary.message.startswith("Please confirm this order:")
    assert "Blue Mug" in summary.message
    assert "Subtotal:" in summary.message
    assert "Recipient: Ada" in summary.message
    assert "Phone: +98912" in summary.message
    assert "Address: Tehran" in summary.message
    assert "Note: Leave at door" in summary.message

    db_session.query(CartItem).filter(CartItem.user_id == user_a.id).update({"unit_price": None})
    db_session.commit()
    blocked = _run(db_session, user_a, session, {"action": "order_confirm"})
    assert blocked.order is None
    assert blocked.message == "I can't place the order yet because a cart item has no price."
    db_session.refresh(session)
    assert load_checkout_state(session.checkout_state)["phase"] == "awaiting_confirm"
    assert db_session.query(Order).count() == 0


def test_confirm_failure_keeps_draft_and_cart(db_session, user_a, monkeypatch):
    session = _session(db_session, user_a)
    _collect_ready(db_session, user_a, session)

    def boom(*args, **kwargs):
        raise CommerceError("database failed", 500)

    monkeypatch.setattr("app.services.commerce_actions.create_order_from_cart", boom)
    failed = _run(db_session, user_a, session, {"action": "order_confirm"})
    assert failed.order is None
    assert failed.message == "database failed"
    assert db_session.query(Order).count() == 0
    assert db_session.query(CartItem).filter(CartItem.user_id == user_a.id).count() == 1
    db_session.refresh(session)
    assert load_checkout_state(session.checkout_state)["phase"] == "awaiting_confirm"


def test_confirm_places_pending_order_then_cancel_keeps_cart(db_session, user_a):
    session = _session(db_session, user_a)
    _collect_ready(db_session, user_a, session)
    placed = _run(db_session, user_a, session, {"action": "order_confirm"})
    assert placed.cart_updated is True
    assert placed.order["status"] == "pending"
    assert placed.order["total_amount"] == 12.5
    assert f"Order #{placed.order['id']} placed. Status: pending. Total: $12.50." in placed.message
    assert db_session.query(CartItem).filter(CartItem.user_id == user_a.id).count() == 0
    db_session.refresh(session)
    assert load_checkout_state(session.checkout_state)["phase"] == "idle"

    _run(db_session, user_a, session, {"action": "cart_add"}, attached=[MUG])
    _run(db_session, user_a, session, {"action": "checkout_start"})
    cancelled = _run(db_session, user_a, session, {"action": "order_cancel"})
    assert cancelled.message == "Checkout cancelled. Your cart is unchanged."
    assert cancelled.checkout_phase == "idle"
    assert db_session.query(CartItem).filter(CartItem.user_id == user_a.id).count() == 1
    assert db_session.query(Order).count() == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_commerce_execute.py -v`

Expected: FAIL with `ImportError` for `execute_commerce_action` (or `normalize_commerce_action`)

- [ ] **Step 3: Write minimal implementation**

Append the executor to `backend/app/services/commerce_actions.py`. Import `json`, `Session`, `Message`, `CartItemCreate`, `OrderCreate`, the checkout functions, and the commerce service functions at the top of the file.

```python
import json
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.message import Message
from app.schemas.cart import CartItemCreate
from app.schemas.order import OrderCreate
from app.services.checkout_state import (
    begin_collecting,
    dump_checkout_state,
    fill_slots,
    load_checkout_state,
    mark_idle,
    ready_to_confirm,
)
from app.services.commerce import (
    CommerceError,
    add_cart_item,
    create_order_from_cart,
    delete_cart_item,
    get_cart_for_user,
    update_cart_item,
)

ACTIONS = {
    "cart_add",
    "cart_view",
    "cart_update",
    "checkout_start",
    "checkout_fill",
    "order_confirm",
    "order_cancel",
    "clarify_product",
    "none",
}
ASK = {
    "recipient_name": "Who should receive this order? Please send the recipient's full name.",
    "phone": "What phone number should we use for delivery?",
    "address": "What is the delivery address?",
}
EMPTY_CART = "Your cart is empty. Add a product before checkout."
NOT_READY = "I can place the order only after you review the summary and reply yes."
NULL_PRICE = "I can't place the order yet because a cart item has no price."
NO_PRODUCT = "I don't know which product to add. Open a product in the sidebar or pick one of the cards I showed."
CANCELLED = "Checkout cancelled. Your cart is unchanged."
NOT_IN_CART = "I couldn't find that item in your cart."


@dataclass
class CommerceTurn:
    message: str
    cart_updated: bool
    order: dict | None
    checkout_phase: str


def _slot(value):
    if value is None:
        return None
    text = value.strip() if isinstance(value, str) else str(value).strip()
    return text


def normalize_commerce_action(data: dict | None) -> dict:
    raw = data if isinstance(data, dict) else {}
    action = raw.get("action") or "none"
    if action not in ACTIONS:
        action = "none"
    confirm = bool(raw.get("confirm"))
    cancel = bool(raw.get("cancel"))
    if action == "none" and cancel:
        action = "order_cancel"
    elif action == "none" and confirm:
        action = "order_confirm"
    quantity = raw.get("quantity")
    try:
        quantity = int(quantity) if quantity is not None else 1
    except (TypeError, ValueError):
        quantity = 1
    remove = bool(raw.get("remove"))
    if action == "cart_update" and quantity == 0:
        remove = True
    if quantity < 1 and not remove:
        quantity = 1
    ref = raw.get("product_ref") if isinstance(raw.get("product_ref"), dict) else {}
    product_id = ref.get("product_id")
    try:
        product_id = int(product_id) if product_id is not None else None
    except (TypeError, ValueError):
        product_id = None
    hint = ref.get("hint")
    hint = hint.strip() if isinstance(hint, str) and hint.strip() else None
    variant_label = ref.get("variant_label")
    variant_label = variant_label.strip() if isinstance(variant_label, str) else None
    slots_in = raw.get("slots") if isinstance(raw.get("slots"), dict) else {}
    slots = {key: _slot(slots_in.get(key)) for key in ("recipient_name", "phone", "address", "note")}
    return {
        "action": action,
        "quantity": quantity,
        "remove": remove,
        "product_ref": {"hint": hint, "product_id": product_id, "variant_label": variant_label},
        "slots": slots,
        "confirm": confirm,
        "cancel": cancel,
    }


def load_recent_product_cards(db: Session, session_id: int) -> list[dict]:
    rows = (
        db.query(Message)
        .filter(Message.session_id == session_id, Message.role == "assistant", Message.products.isnot(None))
        .order_by(Message.created_at.desc(), Message.id.desc())
        .all()
    )
    for row in rows:
        if not row.products or not str(row.products).strip():
            continue
        try:
            parsed = json.loads(row.products)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, list) and any(isinstance(item, dict) and item.get("product_id") is not None for item in parsed):
            return [item for item in parsed if isinstance(item, dict)]
    return []


def _save_state(db, session, state: dict) -> None:
    session.checkout_state = dump_checkout_state(state)
    db.commit()


def _money(value) -> str:
    return f"${float(value):.2f}"


def format_cart(cart) -> str:
    if not cart.items:
        return "Your cart is empty."
    lines = ["Your cart:"]
    for item in cart.items:
        variant = f" ({item.variant_label})" if item.variant_label else ""
        price = _money(item.unit_price) if item.unit_price is not None else "price unavailable"
        lines.append(f"- {item.subject}{variant} x{item.quantity} @ {price}")
    lines.append(f"Subtotal: {_money(cart.subtotal) if cart.subtotal is not None else 'unavailable'}")
    return "\n".join(lines)


def format_order_summary(cart, state: dict) -> str:
    lines = ["Please confirm this order:"]
    for item in cart.items:
        variant = f" ({item.variant_label})" if item.variant_label else ""
        price = _money(item.unit_price) if item.unit_price is not None else "price unavailable"
        lines.append(f"- {item.subject}{variant} x{item.quantity} @ {price}")
    lines.append(f"Subtotal: {_money(cart.subtotal) if cart.subtotal is not None else 'unavailable'}")
    lines.append(f"Recipient: {state.get('recipient_name')}")
    lines.append(f"Phone: {state.get('phone')}")
    lines.append(f"Address: {state.get('address')}")
    if state.get("note"):
        lines.append(f"Note: {state.get('note')}")
    lines.append('Reply "yes" to place the order, or "cancel" to stop.')
    return "\n".join(lines)


def _resolve_message(resolved: ResolveProduct) -> str:
    if resolved.status == "none":
        return NO_PRODUCT
    if resolved.status == "need_variant":
        subject = resolved.candidates[0]["subject"] if resolved.candidates else "this product"
        lines = [f"Which variant of {subject} should I add?"]
        for index, label in enumerate(resolved.variant_options, start=1):
            lines.append(f"{index}. {label}")
        return "\n".join(lines)
    lines = ["Which product should I add?"]
    for index, candidate in enumerate(resolved.candidates, start=1):
        price = candidate.get("price")
        suffix = f" — {_money(price)}" if isinstance(price, (int, float)) else ""
        lines.append(f"{index}. {candidate.get('subject')}{suffix}")
    return "\n".join(lines)


def _turn(message: str, state: dict, *, cart_updated: bool = False, order: dict | None = None) -> CommerceTurn:
    return CommerceTurn(message=message, cart_updated=cart_updated, order=order, checkout_phase=state["phase"])


def execute_commerce_action(
    db: Session,
    user_id: int,
    session,
    action: dict,
    *,
    attached_products: list[dict],
    sidebar_product: dict | None,
    recent_products: list[dict] | None = None,
) -> CommerceTurn:
    action = normalize_commerce_action(action)
    state = load_checkout_state(session.checkout_state)
    if recent_products is None:
        recent_products = load_recent_product_cards(db, session.id)
    name = action["action"]

    if name == "cart_view":
        return _turn(format_cart(get_cart_for_user(db, user_id)), state)

    if name in ("cart_add", "clarify_product"):
        resolved = resolve_product_for_cart(
            attached_products,
            sidebar_product,
            recent_products,
            action["product_ref"],
        )
        if name == "clarify_product":
            if resolved.status == "selected" and resolved.product:
                return _turn(f"Which product should I add?\n1. {resolved.product['subject']}", state)
            return _turn(_resolve_message(resolved), state)
        if resolved.status != "selected":
            return _turn(_resolve_message(resolved), state)
        snap = resolved.product
        add_cart_item(
            db,
            user_id,
            CartItemCreate(
                product_id=snap["product_id"],
                subject=snap["subject"],
                unit_price=snap["unit_price"],
                image_url=snap["image_url"],
                category_name=snap["category_name"],
                variant_label=snap["variant_label"],
                quantity=action["quantity"],
            ),
        )
        db.refresh(session)
        state = load_checkout_state(session.checkout_state)
        variant = f" ({snap['variant_label']})" if snap["variant_label"] else ""
        message = f"Added {action['quantity']} × {snap['subject']}{variant} to your cart."
        if state["phase"] == "awaiting_confirm":
            message += "\n\n" + format_order_summary(get_cart_for_user(db, user_id), state)
        return _turn(message, state, cart_updated=True)

    if name == "cart_update":
        cart = get_cart_for_user(db, user_id)
        ref = action["product_ref"]
        items = list(cart.items)
        if ref.get("product_id") is not None:
            matched = [item for item in items if item.product_id == ref["product_id"]]
        elif len(items) == 1:
            matched = items
        else:
            matched = []
        if len(matched) == 0:
            message = NOT_IN_CART if items else EMPTY_CART
            if len(items) > 1 and ref.get("product_id") is None:
                message = "Which cart item should I change?\n" + "\n".join(
                    f"- {item.subject}" + (f" ({item.variant_label})" if item.variant_label else "")
                    for item in items
                )
            return _turn(message, state)
        if len(matched) > 1:
            message = "Which cart item should I change?\n" + "\n".join(f"- {item.subject}" for item in matched)
            return _turn(message, state)
        target = matched[0]
        if action["remove"]:
            delete_cart_item(db, user_id, target.id)
            message = f"Removed {target.subject} from your cart."
        else:
            update_cart_item(db, user_id, target.id, action["quantity"])
            message = f"Updated {target.subject} to quantity {action['quantity']}."
        db.refresh(session)
        state = load_checkout_state(session.checkout_state)
        return _turn(message, state, cart_updated=True)

    if name in ("checkout_start", "checkout_fill"):
        if state["phase"] == "idle" and not get_cart_for_user(db, user_id).items:
            return _turn(EMPTY_CART, state)
        state = begin_collecting(state) if name == "checkout_start" else fill_slots(state, action["slots"])
        _save_state(db, session, state)
        if state["phase"] == "awaiting_confirm":
            return _turn(format_order_summary(get_cart_for_user(db, user_id), state), state)
        return _turn(ASK[state["next_slot"]], state)

    if name == "order_confirm":
        if state["phase"] != "awaiting_confirm":
            return _turn(NOT_READY, state)
        if any(value not in (None, "") for value in action["slots"].values()):
            state = fill_slots(state, action["slots"])
            _save_state(db, session, state)
            if state["phase"] != "awaiting_confirm":
                return _turn(ASK[state["next_slot"]], state)
        if not ready_to_confirm(state):
            return _turn(NOT_READY, state)
        cart = get_cart_for_user(db, user_id)
        if not cart.items:
            return _turn(EMPTY_CART, state)
        if not cart.checkout_ready:
            return _turn(NULL_PRICE, state)
        idle = mark_idle()
        session.checkout_state = dump_checkout_state(idle)
        try:
            order = create_order_from_cart(
                db,
                user_id,
                OrderCreate(
                    recipient_name=state["recipient_name"],
                    phone=state["phone"],
                    address=state["address"],
                    note=state.get("note"),
                ),
            )
        except CommerceError as err:
            db.rollback()
            db.refresh(session)
            kept = load_checkout_state(session.checkout_state)
            return _turn(err.detail, kept)
        payload = {"id": order.id, "total_amount": float(order.total_amount), "status": order.status}
        message = f"Order #{order.id} placed. Status: pending. Total: ${order.total_amount:.2f}."
        return _turn(message, idle, cart_updated=True, order=payload)

    if name == "order_cancel":
        state = mark_idle()
        _save_state(db, session, state)
        return _turn(CANCELLED, state)

    return _turn("I couldn't do that.", state)
```

`cart_view` on an empty cart must return a message that contains `Your cart is empty.` The `format_cart` string `Your cart is empty.` satisfies the user-isolation test. Do not reuse `EMPTY_CART` there. `clarify_product` never calls `add_cart_item`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_commerce_execute.py tests/test_product_resolve.py tests/test_cart.py tests/test_orders.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/commerce_actions.py backend/tests/test_commerce_execute.py
git commit -m "$(cat <<'EOF'
feat: execute chat commerce actions on cart and orders

EOF
)"
```

---

### Task 6: Detect a commerce action as JSON

**Files:**
- Modify: `backend/app/services/commerce_actions.py`
- Test: `backend/tests/test_commerce_detector.py`

**Interfaces:**
- Consumes: `normalize_commerce_action` from Task 5
- Produces: `detect_commerce_action(message: str | None, checkout_phase: str, *, complete=None) -> dict` returning the normalized action dict. The default completer calls AvalAI at temperature 0 and is not used by tests. Inject `complete(prompt: str) -> str`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_commerce_detector.py`:

```python
from app.services.commerce_actions import detect_commerce_action


def test_blank_message_is_none():
    assert detect_commerce_action("  ", "collecting", complete=lambda prompt: '{"action":"cart_add"}')["action"] == "none"


def test_parse_cart_add_json():
    def complete(prompt: str) -> str:
        assert "Blue Mug" in prompt
        return '{"action":"cart_add","quantity":2,"product_ref":{"hint":null,"product_id":null,"variant_label":null},"slots":{},"confirm":false,"cancel":false}'

    action = detect_commerce_action("add two", "idle", complete=complete)
    assert action["action"] == "cart_add"
    assert action["quantity"] == 2


def test_garbage_json_is_none():
    action = detect_commerce_action("hello", "idle", complete=lambda prompt: "sure, I can help")
    assert action["action"] == "none"


def test_collecting_prompt_prefers_checkout_over_search():
    seen = {}

    def complete(prompt: str) -> str:
        seen["prompt"] = prompt
        return '{"action":"checkout_fill","slots":{"address":"Tehran, Valiasr"}}'

    action = detect_commerce_action("Tehran, Valiasr", "collecting", complete=complete)
    assert "collecting" in seen["prompt"]
    assert "Tehran, Valiasr" in seen["prompt"]
    assert "unless the user is clearly starting a new product search" in seen["prompt"]
    assert action["action"] == "checkout_fill"
    assert action["slots"]["address"] == "Tehran, Valiasr"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_commerce_detector.py -v`

Expected: FAIL with `ImportError: cannot import name 'detect_commerce_action'`

- [ ] **Step 3: Write minimal implementation**

Append to `backend/app/services/commerce_actions.py`:

```python
def _detector_prompt(message: str, phase: str) -> str:
    return f"""You classify a shopping-assistant utterance into one commerce action. Respond with ONLY a JSON object.

Current checkout phase: "{phase}"
User message: {json.dumps(message)}

The user may write in any language.
If phase is collecting or awaiting_confirm, treat the message as checkout (checkout_fill, order_confirm, or order_cancel) unless the user is clearly starting a new product search.
If they are clearly starting a new product search, return action "none".
Do not search the catalog yourself. Do not invent product ids.

JSON schema:
{{
  "action": "cart_add" | "cart_view" | "cart_update" | "checkout_start" | "checkout_fill" | "order_confirm" | "order_cancel" | "clarify_product" | "none",
  "quantity": 1,
  "remove": false,
  "product_ref": {{"hint": "first" | "this" | null, "product_id": null, "variant_label": null}},
  "slots": {{"recipient_name": null, "phone": null, "address": null, "note": null}},
  "confirm": false,
  "cancel": false
}}

Rules:
- cart_add: user wants the current product or shown cards added. Put a color or size in product_ref.variant_label when they name one. quantity defaults to 1.
- cart_view: user asks what is in the cart.
- cart_update: user changes a quantity. remove true when they want the line deleted. product_ref.product_id stays null unless the message contains an id.
- checkout_start: user wants to order, check out, or place the order and checkout has not started.
- checkout_fill: user is giving recipient_name, phone, address, or note. Copy only the values they actually gave.
- order_confirm: user explicitly agrees to place the order (yes, confirm, place it, بله, تایید). Set confirm true.
- order_cancel: user aborts checkout. Set cancel true.
- clarify_product: user refers to a product but not one specific card.
- none: greeting, product search, store question, FAQ, or anything that is not a cart or checkout action.
"""


def _llm_complete(prompt: str) -> str:
    from langchain_core.messages import HumanMessage
    from langchain_openai import ChatOpenAI

    from app.config import AVALAI_API_KEY
    from app.services.rag import _avalai_chat_kwargs

    if not AVALAI_API_KEY:
        return ""
    llm = ChatOpenAI(**_avalai_chat_kwargs(temperature=0, max_tokens=300))
    response = llm.invoke([HumanMessage(content=prompt)])
    content = response.content if hasattr(response, "content") else str(response)
    return content or ""


def _extract_first_json_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for index, char in enumerate(text[start:], start=start):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def detect_commerce_action(message: str | None, checkout_phase: str, *, complete=None) -> dict:
    if not message or not str(message).strip():
        return normalize_commerce_action(None)
    phase = checkout_phase if checkout_phase in ("idle", "collecting", "awaiting_confirm") else "idle"
    prompt = _detector_prompt(str(message).strip(), phase)
    raw_text = _llm_complete(prompt) if complete is None else complete(prompt)
    json_str = _extract_first_json_object(raw_text or "")
    data = None
    if json_str:
        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            data = parsed
    return normalize_commerce_action(data)
```

`_llm_complete` is the only place that imports AvalAI, and only when `complete` is omitted. Tests pass `complete`, so they do not import Qdrant.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_commerce_detector.py tests/test_commerce_execute.py -v`

Expected: PASS. The detector test must not call the network. If a test hangs on AvalAI, `complete` is not being used.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/commerce_actions.py backend/tests/test_commerce_detector.py
git commit -m "$(cat <<'EOF'
feat: detect commerce actions as JSON

EOF
)"
```

---

### Task 7: Run commerce from chat and voice

**Files:**
- Modify: `backend/app/api/chat.py` (`_run_chat_response`, `POST /chat`, `POST /voice-chat`)
- Test: `backend/tests/test_chat_commerce.py`

**Interfaces:**
- Consumes:
  - `detect_commerce_action(message, phase) -> normalized action`
  - `execute_commerce_action(...) -> CommerceTurn` with `.message`, `.cart_updated`, `.order`, `.checkout_phase`
  - `load_checkout_state`
  - Existing RAG helpers already imported in `chat.py`: `detect_intent_with_llm`, `run_rag_response`, `enhanced_search_with_llm`, `get_query_vector`, `search_store`, `search_faq`, `build_combined_context`, `products_from_search_results`, `is_broad_products_query`, `reorder_products_by_mention`, `detect_emotion_with_llm`, `_format_product_context`, `_get_last_shown_products`
- Produces:
  - `@dataclass ChatTurnResult` in `chat.py`: `message: str`, `products: list`, `suggested_emotion: str`, `cart_updated: bool = False`, `order: dict | None = None`, `checkout_phase: str | None = None`
  - `POST /api/chat` and `POST /api/voice-chat` JSON: existing `message`, `products`, `suggested_emotion`, plus `cart_updated`, `order`, `checkout_phase`. Voice also returns `transcribed_text` and optional `audio_base64`.
  - Form fields on both endpoints: `selected_products: str | None`, `sidebar_product: str | None`
  - `_run_chat_response(db, session, user_id, user_text, image_bytes=None, top_k=None, price_max=None, category=None, attached_products=None, sidebar_product=None) -> ChatTurnResult`
  - Message rows are written on the request `db` session. Do not open `SessionLocal()` inside the turn. Today `_run_chat_response` returns three values and both endpoints unpack three values; the docstring that says `tuple[str, list]` is stale.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_chat_commerce.py`. Build a tiny app in the test so the real FastAPI lifespan does not load CLIP or Whisper. Patch names on `app.api.chat` because the handlers use those imported names.

```python
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import cart as cart_api
from app.api import chat as chat_api
from app.api import orders as orders_api
from app.core.database import get_db
from app.models.cart import CartItem
from app.models.order import Order
from app.models.session import ChatSession
from app.services.checkout_state import dump_checkout_state, empty_state, load_checkout_state
from app.services.commerce_actions import normalize_commerce_action

MUG = {
    "product_id": 101,
    "subject": "Blue Mug",
    "price": 12.5,
    "image_url": "https://example.com/mug.jpg",
    "category_name": "Home",
    "variants": [],
}


@pytest.fixture()
def chat_client(db_session):
    app = FastAPI()
    app.include_router(chat_api.router, prefix="/api")
    app.include_router(cart_api.router, prefix="/api")
    app.include_router(orders_api.router, prefix="/api")

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _session(db, user) -> ChatSession:
    row = ChatSession(user_id=user.id, title="New Chat")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _patch_quiet(monkeypatch):
    monkeypatch.setattr(chat_api, "detect_emotion_with_llm", lambda *args, **kwargs: "neutral")

    async def no_audio(text, lang=None):
        return None

    monkeypatch.setattr(chat_api, "text_to_speech_to_bytes", no_audio)


def test_idle_none_action_still_searches(chat_client, db_session, user_a, auth_header_a, monkeypatch):
    session = _session(db_session, user_a)
    calls = {"search": 0, "rag": 0}
    _patch_quiet(monkeypatch)
    monkeypatch.setattr(
        chat_api,
        "detect_commerce_action",
        lambda message, phase: normalize_commerce_action({"action": "none"}),
    )
    monkeypatch.setattr(
        chat_api,
        "detect_intent_with_llm",
        lambda message: {"needs_qdrant_search": True, "intent_type": "product_search", "confidence": 1.0},
    )

    def fake_enhanced(**kwargs):
        calls["search"] += 1
        return {"results": []}

    def fake_rag(*args, **kwargs):
        calls["rag"] += 1
        return "Here are some mugs"

    monkeypatch.setattr(chat_api, "enhanced_search_with_llm", fake_enhanced)
    monkeypatch.setattr(chat_api, "get_query_vector", lambda *args, **kwargs: [0.0])
    monkeypatch.setattr(chat_api, "search_store", lambda *args, **kwargs: [])
    monkeypatch.setattr(chat_api, "search_faq", lambda *args, **kwargs: [])
    monkeypatch.setattr(chat_api, "build_combined_context", lambda *args, **kwargs: "ctx")
    monkeypatch.setattr(chat_api, "products_from_search_results", lambda results: [])
    monkeypatch.setattr(chat_api, "is_broad_products_query", lambda text: True)
    monkeypatch.setattr(chat_api, "run_rag_response", fake_rag)

    response = chat_client.post(
        "/api/chat",
        data={"session_id": str(session.id), "message": "show me mugs"},
        headers=auth_header_a,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Here are some mugs"
    assert body["cart_updated"] is False
    assert body["order"] is None
    assert body["checkout_phase"] == "idle"
    assert calls == {"search": 1, "rag": 1}


def test_chat_add_then_checkout_confirm(chat_client, db_session, user_a, user_b, auth_header_a, monkeypatch):
    session = _session(db_session, user_a)
    _session(db_session, user_b)
    script = [
        {"action": "cart_add", "quantity": 1},
        {"action": "checkout_start"},
        {"action": "checkout_fill", "slots": {"recipient_name": "Ada", "phone": "+98912", "address": "Tehran"}},
        {"action": "order_confirm"},
    ]

    def fake_detect(message, phase):
        return normalize_commerce_action(script.pop(0))

    rag_calls = {"n": 0}
    _patch_quiet(monkeypatch)
    monkeypatch.setattr(chat_api, "detect_commerce_action", fake_detect)
    monkeypatch.setattr(chat_api, "run_rag_response", lambda *args, **kwargs: rag_calls.__setitem__("n", rag_calls["n"] + 1))

    def post(text, extra=None):
        data = {"session_id": str(session.id), "message": text}
        if extra:
            data.update(extra)
        return chat_client.post("/api/chat", data=data, headers=auth_header_a)

    added = post("add this", {"selected_products": json.dumps([MUG]), "sidebar_product": "not-json"})
    assert added.status_code == 200
    assert added.json()["cart_updated"] is True
    assert added.json()["order"] is None
    assert "Blue Mug" in added.json()["message"]

    started = post("I want to order")
    assert started.json()["checkout_phase"] == "collecting"
    filled = post("Ada, +98912, Tehran")
    assert filled.json()["checkout_phase"] == "awaiting_confirm"
    assert "Please confirm this order:" in filled.json()["message"]
    done = post("yes")
    body = done.json()
    assert body["cart_updated"] is True
    assert body["order"]["status"] == "pending"
    assert body["order"]["total_amount"] == 12.5
    assert body["checkout_phase"] == "idle"
    assert rag_calls["n"] == 0
    assert db_session.query(CartItem).filter(CartItem.user_id == user_a.id).count() == 0
    assert db_session.query(Order).filter(Order.user_id == user_b.id).count() == 0
    assert db_session.query(Order).filter(Order.user_id == user_a.id).count() == 1


def test_collecting_phase_is_passed_and_skips_search(chat_client, db_session, user_a, auth_header_a, monkeypatch):
    session = _session(db_session, user_a)
    state = {**empty_state(), "phase": "collecting", "next_slot": "address", "recipient_name": "Ada", "phone": "+1"}
    session.checkout_state = dump_checkout_state(state)
    db_session.commit()
    seen = {}

    def fake_detect(message, phase):
        seen["phase"] = phase
        seen["message"] = message
        return normalize_commerce_action({"action": "checkout_fill", "slots": {"address": "1 Main St"}})

    _patch_quiet(monkeypatch)
    monkeypatch.setattr(chat_api, "detect_commerce_action", fake_detect)
    monkeypatch.setattr(chat_api, "enhanced_search_with_llm", lambda **kwargs: (_ for _ in ()).throw(AssertionError("search")))
    response = chat_client.post(
        "/api/chat",
        data={"session_id": str(session.id), "message": "1 Main St"},
        headers=auth_header_a,
    )
    assert response.status_code == 200
    assert seen == {"phase": "collecting", "message": "1 Main St"}
    assert response.json()["checkout_phase"] == "awaiting_confirm"
    db_session.refresh(session)
    assert load_checkout_state(session.checkout_state)["address"] == "1 Main St"


def test_voice_uses_same_commerce_path(chat_client, db_session, user_a, auth_header_a, monkeypatch):
    session = _session(db_session, user_a)
    _patch_quiet(monkeypatch)
    monkeypatch.setattr(chat_api, "transcribe_audio", lambda path: "add this mug")
    monkeypatch.setattr(
        chat_api,
        "detect_commerce_action",
        lambda message, phase: normalize_commerce_action({"action": "cart_add", "quantity": 1}),
    )
    response = chat_client.post(
        "/api/voice-chat",
        data={"session_id": str(session.id), "selected_products": json.dumps([MUG])},
        files={"voice": ("clip.webm", b"fake-audio", "audio/webm")},
        headers=auth_header_a,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["transcribed_text"] == "add this mug"
    assert body["cart_updated"] is True
    assert "Blue Mug" in body["message"]
    assert db_session.query(CartItem).filter(CartItem.user_id == user_a.id).count() == 1


def test_image_turn_skips_commerce(chat_client, db_session, user_a, auth_header_a, monkeypatch):
    session = _session(db_session, user_a)
    _patch_quiet(monkeypatch)

    def forbid_commerce(*args, **kwargs):
        raise AssertionError("commerce detector")

    monkeypatch.setattr(chat_api, "detect_commerce_action", forbid_commerce)
    monkeypatch.setattr(chat_api, "run_embed_and_search", lambda *args, **kwargs: [])
    monkeypatch.setattr(chat_api, "get_query_vector", lambda *args, **kwargs: [0.0])
    monkeypatch.setattr(chat_api, "search_store", lambda *args, **kwargs: [])
    monkeypatch.setattr(chat_api, "search_faq", lambda *args, **kwargs: [])
    monkeypatch.setattr(chat_api, "build_combined_context", lambda *args, **kwargs: "ctx")
    monkeypatch.setattr(chat_api, "products_from_search_results", lambda results: [])
    monkeypatch.setattr(chat_api, "is_broad_products_query", lambda text: True)
    monkeypatch.setattr(chat_api, "run_rag_response", lambda *args, **kwargs: "similar products")
    response = chat_client.post(
        "/api/chat",
        data={"session_id": str(session.id), "message": ""},
        files={"image": ("x.jpg", b"\xff\xd8\xff", "image/jpeg")},
        headers=auth_header_a,
    )
    assert response.status_code == 200
    assert response.json()["message"] == "similar products"
    assert response.json()["cart_updated"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_chat_commerce.py -v`

Expected: FAIL. `/api/chat` returns no `cart_updated` (KeyError or assertion). The voice test fails the same way. Importing `app.api.chat` is expected to load the RAG modules; do not skip the file for that.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/api/chat.py`:

- Add `from dataclasses import dataclass`.
- Drop `SessionLocal` from the database import if nothing else uses it.
- Import `load_checkout_state`, `detect_commerce_action`, and `execute_commerce_action`.

```python
from dataclasses import dataclass

from app.services.checkout_state import load_checkout_state
from app.services.commerce_actions import detect_commerce_action, execute_commerce_action
```

```python
@dataclass
class ChatTurnResult:
    message: str
    products: list
    suggested_emotion: str
    cart_updated: bool = False
    order: dict | None = None
    checkout_phase: str | None = None


def _parse_product_list(raw: str | None) -> list[dict]:
    if not raw or not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _parse_product_object(raw: str | None) -> dict | None:
    if not raw or not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _persist_turn(db: Session, session: ChatSession, user_text: str, assistant_text: str, products: list | None) -> None:
    db.add(Message(session_id=session.id, role="user", content=user_text, image_url=None))
    db.add(
        Message(
            session_id=session.id,
            role="assistant",
            content=assistant_text,
            products=json.dumps(products) if products else None,
        )
    )
    if session.title == "New Chat" and user_text:
        session.title = user_text[:100] + ("..." if len(user_text) > 100 else "")
    db.commit()


def _chat_payload(result: ChatTurnResult) -> dict:
    return {
        "message": result.message,
        "products": result.products,
        "suggested_emotion": result.suggested_emotion,
        "cart_updated": result.cart_updated,
        "order": result.order,
        "checkout_phase": result.checkout_phase,
    }
```

Replace `_run_chat_response` with this function. The search block is the current one, with `session.id` instead of `session_id`, `rag_message` passed only to `run_rag_response`, and `_persist_turn` instead of `SessionLocal()`.

```python
async def _run_chat_response(
    db: Session,
    session: ChatSession,
    user_id: int,
    user_text: str,
    image_bytes: bytes | None = None,
    top_k: int | None = None,
    price_max: float | None = None,
    category: str | None = None,
    attached_products: list[dict] | None = None,
    sidebar_product: dict | None = None,
) -> ChatTurnResult:
    loop = asyncio.get_event_loop()
    attached_products = attached_products or []
    phase = load_checkout_state(session.checkout_state)["phase"]
    search_text = None if user_text == "(user sent an image)" else (user_text or None)

    if not image_bytes:
        action = await loop.run_in_executor(
            _executor,
            lambda text=user_text, current=phase: detect_commerce_action(text, current),
        )
        if action.get("action") != "none":
            turn = execute_commerce_action(
                db,
                user_id,
                session,
                action,
                attached_products=attached_products,
                sidebar_product=sidebar_product,
            )
            emotion = await loop.run_in_executor(
                _executor,
                lambda: detect_emotion_with_llm(user_text, turn.message),
            )
            if not emotion:
                emotion = "neutral"
            _persist_turn(db, session, user_text, turn.message, products=None)
            return ChatTurnResult(
                message=turn.message,
                products=[],
                suggested_emotion=emotion,
                cart_updated=turn.cart_updated,
                order=turn.order,
                checkout_phase=turn.checkout_phase,
            )

    intent_type = "product_search"
    if image_bytes:
        do_product_search = True
    else:
        intent_result = await loop.run_in_executor(
            _executor,
            lambda text=search_text: detect_intent_with_llm(text),
        )
        do_product_search = intent_result.get("needs_qdrant_search", False)
        intent_type = intent_result.get("intent_type", "unknown")

    include_products = do_product_search and intent_type not in ("store_info", "faq")
    rag_message = user_text
    if attached_products:
        rag_message = _format_product_context(attached_products) + user_text

    if do_product_search:
        search_results: list[dict] = []
        products: list[dict] = []
        if include_products:
            if image_bytes:
                search_results = await loop.run_in_executor(
                    _executor,
                    lambda text=search_text: run_embed_and_search(
                        text, image_bytes, top_k=top_k, price_max=price_max, category=category
                    ),
                )
            else:
                last_shown = _get_last_shown_products(db, session.id)
                enhanced = await loop.run_in_executor(
                    _executor,
                    lambda text=search_text: enhanced_search_with_llm(
                        user_query=text or "",
                        limit=top_k or 3,
                        price_max=price_max,
                        category=category,
                        last_shown_products=last_shown,
                    ),
                )
                search_results = enhanced["results"]
            if not is_broad_products_query(search_text):
                search_results = filter_search_results_by_min_score(search_results)
            products = products_from_search_results(search_results)
        query_vector = await loop.run_in_executor(
            _executor,
            lambda text=search_text: get_query_vector(text, image_bytes),
        )
        store_results = await loop.run_in_executor(
            _executor,
            lambda vector=query_vector: search_store(vector, top_k=3),
        )
        faq_results = await loop.run_in_executor(
            _executor,
            lambda vector=query_vector: search_faq(vector, top_k=5),
        )
        context = build_combined_context(store_results, faq_results, search_results)
    else:
        context = "No relevant products found."
        products = []

    history = get_chat_history(db, session.id)
    search_by_image = image_bytes is not None
    try:
        full_text = await loop.run_in_executor(
            _executor,
            lambda: run_rag_response(context, history, rag_message, search_by_image=search_by_image),
        )
    except Exception as exc:
        _raise_llm_http_error(exc)

    if products and full_text:
        products = reorder_products_by_mention(full_text, products)

    suggested_emotion = await loop.run_in_executor(
        _executor,
        lambda: detect_emotion_with_llm(user_text, full_text),
    )
    if suggested_emotion is None:
        suggested_emotion = "neutral"

    _persist_turn(db, session, user_text, full_text, products)
    return ChatTurnResult(
        message=full_text,
        products=products,
        suggested_emotion=suggested_emotion,
        cart_updated=False,
        order=None,
        checkout_phase=phase,
    )
```

`query_vector` is assigned inside the `if do_product_search` block before the lambdas that default it. That matches the current control flow. Keep `filter_search_results_by_min_score` imported as it is today.

Change `POST /chat` to accept the two form fields and return `_chat_payload`. Keep the session ownership check, image read, empty-message check, and `top_k` check.

```python
    selected_products: str | None = Form(None),
    sidebar_product: str | None = Form(None),
```

```python
    user_text = message.strip() or "(user sent an image)"
    result = await _run_chat_response(
        db,
        session,
        current_user.id,
        user_text,
        image_bytes=image_bytes,
        top_k=top_k,
        price_max=price_max,
        category=category,
        attached_products=_parse_product_list(selected_products),
        sidebar_product=_parse_product_object(sidebar_product),
    )
    return _chat_payload(result)
```

Change `POST /voice-chat` the same way. Delete the block that prefixes `_format_product_context` onto the transcript. Pass the raw transcript.

```python
    selected_products: str | None = Form(None),
    sidebar_product: str | None = Form(None),
```

```python
    user_text = text.strip()
    result = await _run_chat_response(
        db,
        session,
        current_user.id,
        user_text,
        image_bytes=None,
        attached_products=_parse_product_list(selected_products),
        sidebar_product=_parse_product_object(sidebar_product),
    )
    payload = _chat_payload(result)
    payload["transcribed_text"] = user_text
    audio_base64 = None
    try:
        audio_bytes = await text_to_speech_to_bytes(result.message)
        if audio_bytes:
            audio_base64 = base64.b64encode(audio_bytes).decode("ascii")
    except Exception:
        pass
    if audio_base64 is not None:
        payload["audio_base64"] = audio_base64
    return payload
```

Leave `/detect-intent` and `/voice-detect-intent` unchanged.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && ./venv/bin/python -m pytest tests/test_chat_commerce.py tests/test_commerce_execute.py tests/test_cart.py tests/test_orders.py -v`

Expected: PASS. `test_chat_add_then_checkout_confirm` creates one pending order for user A, clears A's cart, and leaves user B with no order.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/chat.py backend/tests/test_chat_commerce.py
git commit -m "$(cat <<'EOF'
feat: run commerce actions from chat and voice

EOF
)"
```

---

### Task 8: Refresh the cart from chat replies

**Files:**
- Create: `frontend/lib/commerceChat.mjs`
- Create: `frontend/lib/commerceChat.test.mjs`
- Modify: `frontend/lib/api.ts` (`SendChatResult`, `SendVoiceChatResult`, `sendChat`, `sendVoiceChat`)
- Modify: `frontend/components/chat/ProductSidebar.tsx` (props and variant clicks)
- Modify: `frontend/components/chat/ChatPanel.tsx` (`handleSend`, `handleSendVoice`, sidebar state)

**Interfaces:**
- Consumes: chat JSON `cart_updated` and `order: {id, total_amount, status} | null`; `ProductSummary` and `ProductVariant` from `frontend/lib/api.ts`; `useCart().refresh`
- Produces:
  - `variantLabel(variant) -> string`
  - `buildSidebarProduct(product, selectedVariant) -> sidebar snapshot | null` with `product_id`, `subject`, `price`, `image_url`, `category_name`, `variants`, `selected_variant_label`
  - `commerceFollowUp(result) -> {refreshCart: boolean, orderToast: string | null}`
  - `sendChat` options gain `selectedProducts` and `sidebarProduct`
  - `sendVoiceChat(sessionId, voiceFile, selectedProducts?, sidebarProduct?)`
  - No new chat buttons. Do not change `CartSheet` or `CartHeaderButton`.

- [ ] **Step 1: Write the failing test**

Create `frontend/lib/commerceChat.test.mjs`:

```javascript
import assert from "node:assert/strict";
import test from "node:test";
import { buildSidebarProduct, commerceFollowUp, variantLabel } from "./commerceChat.mjs";

test("variant label uses attributes", () => {
  assert.equal(
    variantLabel({ attributes: [{ name: "Color", value: "Blue" }] }),
    "Color: Blue"
  );
});

test("sidebar snapshot keeps the selected variant price and image", () => {
  const snap = buildSidebarProduct(
    {
      product_id: 202,
      subject: "Shirt",
      price: 20,
      image_url: null,
      category_name: "Clothes",
      variants: [{ price: 22, image: "https://example.com/blue.jpg" }],
    },
    {
      price: 22,
      image: "https://example.com/blue.jpg",
      attributes: [{ name: "Color", value: "Blue" }],
    }
  );
  assert.equal(snap.selected_variant_label, "Color: Blue");
  assert.equal(snap.price, 22);
  assert.equal(snap.image_url, "https://example.com/blue.jpg");
  assert.equal(snap.product_id, 202);
});

test("missing product and missing variant", () => {
  assert.equal(buildSidebarProduct(null, null), null);
  const snap = buildSidebarProduct(
    { product_id: 1, subject: "Mug", price: 12.5, image_url: "https://example.com/m.jpg", category_name: "Home" },
    null
  );
  assert.equal(snap.selected_variant_label, null);
  assert.equal(snap.price, 12.5);
});

test("commerce follow-up refreshes and toasts only when the server says so", () => {
  assert.deepEqual(commerceFollowUp({ cart_updated: true, order: null }), {
    refreshCart: true,
    orderToast: null,
  });
  assert.deepEqual(commerceFollowUp({ cart_updated: true, order: { id: 9, total_amount: 12.5, status: "pending" } }), {
    refreshCart: true,
    orderToast: "Order #9 placed",
  });
  assert.deepEqual(commerceFollowUp({ cart_updated: false }), {
    refreshCart: false,
    orderToast: null,
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test frontend/lib/commerceChat.test.mjs`

Expected: FAIL because `frontend/lib/commerceChat.mjs` does not exist.

- [ ] **Step 3: Write minimal implementation**

Create `frontend/lib/commerceChat.mjs`:

```javascript
export function variantLabel(variant) {
  if (!variant) return "";
  const attrs = Array.isArray(variant.attributes) ? variant.attributes : [];
  const parts = attrs
    .map((attr) => {
      const name = (attr?.name || "").trim();
      const value = (attr?.value || "").trim();
      if (name && value) return `${name}: ${value}`;
      return value || name || "";
    })
    .filter(Boolean);
  if (parts.length) return parts.join(" · ");
  return (variant.name || variant.color || "").trim();
}

export function buildSidebarProduct(product, selectedVariant) {
  if (!product || product.product_id == null) return null;
  const label = selectedVariant ? variantLabel(selectedVariant) : "";
  const price =
    selectedVariant && selectedVariant.price != null ? selectedVariant.price : product.price ?? null;
  const variantImage = selectedVariant?.image && String(selectedVariant.image).trim();
  return {
    product_id: product.product_id,
    subject: product.subject || "",
    price,
    image_url: variantImage || product.image_url || null,
    category_name: product.category_name || "",
    variants: Array.isArray(product.variants) ? product.variants : [],
    selected_variant_label: label || null,
  };
}

export function commerceFollowUp(result) {
  const orderId = result && result.order && result.order.id != null ? result.order.id : null;
  return {
    refreshCart: Boolean(result && result.cart_updated),
    orderToast: orderId != null ? `Order #${orderId} placed` : null,
  };
}
```

In `frontend/lib/api.ts`, extend the result types and send the form fields. Add:

```typescript
export type SidebarProductSnapshot = {
  product_id: number;
  subject: string;
  price: number | null;
  image_url: string | null;
  category_name: string;
  variants?: ProductVariant[];
  selected_variant_label?: string | null;
};

export type ChatCommerceOrder = {
  id: number;
  total_amount: number;
  status: string;
};
```

Add optional `cart_updated?: boolean`, `order?: ChatCommerceOrder | null`, and `checkout_phase?: string | null` to `SendChatResult` and `SendVoiceChatResult`.

Change `sendChat` options to:

```typescript
  options?: {
    topK?: number;
    selectedProducts?: ProductSummary[];
    sidebarProduct?: SidebarProductSnapshot | null;
  }
```

After the existing `top_k` append:

```typescript
  if (options?.selectedProducts && options.selectedProducts.length > 0) {
    formData.append("selected_products", JSON.stringify(options.selectedProducts));
  }
  if (options?.sidebarProduct) {
    formData.append("sidebar_product", JSON.stringify(options.sidebarProduct));
  }
```

Change `sendVoiceChat` to accept the snapshot and append it the same way:

```typescript
export async function sendVoiceChat(
  sessionId: number,
  voiceFile: File,
  selectedProducts?: ProductSummary[],
  sidebarProduct?: SidebarProductSnapshot | null
): Promise<SendVoiceChatResult> {
```

```typescript
  if (sidebarProduct) {
    formData.append("sidebar_product", JSON.stringify(sidebarProduct));
  }
```

In `frontend/components/chat/ProductSidebar.tsx`, extend props and report the variant. Keep `handleAddToCart` as it is.

```typescript
import type { ProductSummary, ProductVariant } from "@/lib/api";
```

```typescript
type Props = {
  product: ProductSummary;
  onClose: () => void;
  onVariantChange?: (variant: ProductVariant | null) => void;
};
```

```typescript
export function ProductSidebar({ product, onClose, onVariantChange }: Props) {
```

```typescript
  useEffect(() => {
    setSelectedVariantIndex(null);
    onVariantChange?.(null);
  }, [product.product_id, onVariantChange]);
```

On the variant button click, after `setSelectedVariantIndex(i)`:

```typescript
onClick={() => {
  setSelectedVariantIndex(i);
  onVariantChange?.(v);
}}
```

In `frontend/components/chat/ChatPanel.tsx`:

- Import `buildSidebarProduct` and `commerceFollowUp` from `@/lib/commerceChat.mjs`.
- Import `ProductVariant` from `@/lib/api` if it is not already imported.
- Change `const { addItem } = useCart()` to `const { addItem, refresh } = useCart()`.
- Add `const [sidebarVariant, setSidebarVariant] = useState<ProductVariant | null>(null);`
- Delete `formatProductContext`. The backend adds that prefix only on the RAG path.
- Pass `onVariantChange={setSidebarVariant}` to `ProductSidebar`. Wrap it in `useCallback` if the effect identity matters:

```tsx
const handleSidebarVariant = useCallback((variant: ProductVariant | null) => {
  setSidebarVariant(variant);
}, []);
```

Inside both `handleSend` and `handleSendVoice`, before the request:

```tsx
  const sidebarPayload = sidebarProduct ? buildSidebarProduct(sidebarProduct, sidebarVariant) : null;
```

`handleSend` must send `message.trim()` as the message, not the old prefixed `effectiveMessage`. Pass products as structured fields:

```tsx
      const result = await sendChat(sessionId, trimmedMessage, imageFile, {
        topK: getTopK(),
        selectedProducts: productsToAttach,
        sidebarProduct: sidebarPayload,
      });
      const { message: responseText, products, suggested_emotion } = result;
```

After the assistant message is appended in both success paths:

```tsx
      const follow = commerceFollowUp(result);
      if (follow.refreshCart) await refresh();
      if (follow.orderToast) toast.success(follow.orderToast);
```

Voice call:

```tsx
      const result = await sendVoiceChat(
        sessionId,
        voiceFile,
        productsToAttach.length > 0 ? productsToAttach : undefined,
        sidebarPayload
      );
```

Use `result.message`, `result.products`, `result.audio_base64`, and `result.suggested_emotion` where the code currently destructures them. Do not add confirm or cancel buttons.

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test frontend/lib/commerceChat.test.mjs`

Expected: PASS (`4 passed`).

Manual check, with the backend and `frontend` dev server running, logged in:

1. Ask for a product, then say “add this” with one card. The header badge count matches `GET /api/cart`.
2. With two cards and no attachment, say “add the first one”. The assistant asks which product and the cart does not gain a line.
3. Open the sidebar, choose a variant, and say “add this”. The cart line uses that variant label and price.
4. Say “I want to order”, answer name, phone, and address, and read the summary. Say “yes”. A pending order exists, the cart is empty, and a toast says `Order #<id> placed`.
5. Repeat through the summary and say “cancel”. No new order row. The cart still has its lines.
6. In a fresh session, ask “show me mugs”. Product search still returns a normal answer while checkout phase is idle.
7. Say the same add phrase by voice. The badge updates after transcription.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/commerceChat.mjs frontend/lib/commerceChat.test.mjs frontend/lib/api.ts frontend/components/chat/ProductSidebar.tsx frontend/components/chat/ChatPanel.tsx
git commit -m "$(cat <<'EOF'
feat: refresh the cart from chat commerce replies

EOF
)"
```

---

## Spec coverage

| Spec requirement | Task |
|------------------|------|
| Checkout JSON on `chat_sessions`, null means idle, startup ensure | Tasks 1–2 |
| Shared cart/order services; HTTP behavior unchanged | Task 3 |
| Pool order, clarify when ambiguous, variant ask, sidebar variant, snapshots, no catalog search | Task 4 |
| Actions, slot order, note optional, summary fields, confirm gate, empty cart, null price, cancel, isolation, no partial order | Task 5 |
| Temperature-0 JSON detector; non-idle checkout beats search unless the model returns `none` | Task 6 |
| `_run_chat_response` for text and voice; `cart_updated`, `order`, `checkout_phase`; image turns stay on RAG; raw utterance stored | Task 7 |
| Client sends `selected_products` and `sidebar_product`; badge refresh and order toast; no new buttons | Task 8 |
| Payment, chips, My Orders, cart-panel redesign, catalog name add | Out of scope; not tasked |

## Self-review

- Placeholder scan: no TBD, TODO, or “implement later” steps. Task 4’s price line is one explicit assignment, not a second algorithm. Task 5’s test step names the three test functions and the reply strings they assert. Task 6 copies the local JSON scanner so the detector test does not import Qdrant.
- Type check: `CommerceTurn.order` is `{id, total_amount, status}`. `ChatTurnResult` uses that object unchanged. `normalize_commerce_action` keys match `execute_commerce_action` and `detect_commerce_action`. `buildSidebarProduct` keys match `resolve_product_for_cart` (`price`, `selected_variant_label`, `variants`).
- `hint: "first"` does not add when several cards are in the pool. That is the spec rule “the first one / the blue one → clarify”. A blue hint can still select a variant after the pool has one product.
