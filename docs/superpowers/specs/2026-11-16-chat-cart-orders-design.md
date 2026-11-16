# Chat cart + simple orders (Approach 1)

**Date:** 2026-11-16  
**Status:** Draft for review  
**Project:** PARAK — Intelligent Shopping Assistant  
**Approach:** Server-side cart + SQLite orders (no payment gateway, no separate catalog)

## Goal

Let logged-in users add products to a cart from the chat experience (product sidebar and product cards), review/edit the cart in a header Sheet/Drawer, and place a simple order with a short checkout form. Orders are stored as `pending` with no payment integration.

## Decisions locked

| Topic | Choice |
|-------|--------|
| Scope shape | Cart from chat only (no browseable catalog page) |
| Checkout depth | Cart + place order (no payment gateway) |
| Auth | Logged-in users only; cart and orders tied to `user_id` |
| Cart UI | Cart icon in chat header + Sheet/Drawer |
| Checkout fields | Recipient name, phone, address, note (optional) |
| Order history UI | Out of scope this phase (no “My orders” page) |
| Persistence | Server-side SQLite cart + orders (not localStorage-only) |

## Non-goals

- Product catalog / shop browse page
- Payment gateway (Zarinpal, Stripe, etc.)
- Guest cart or guest checkout
- “My orders” list page
- Admin order management UI
- Real inventory / stock checks
- LLM / chat-tool “add to cart” as the primary path (may be layered later on the same API)
- Re-pricing from Qdrant at checkout (use cart snapshot prices)

## Architecture

```
ProductSidebar / chat product card
  → POST /api/cart/items  (product snapshot + qty + optional variant)
  → SQLite cart_items (per user)

Chat header (icon + badge)
  → GET /api/cart → Sheet (qty / remove)
  → Checkout form → POST /api/orders
       → create order + order_items from cart snapshots
       → clear cart
       → status = pending
```

Products live primarily in Qdrant today. Cart and order lines store a **snapshot** of display fields so historical orders stay stable if catalog vectors change.

## Data model (SQLite)

### `cart_items`

| Field | Notes |
|-------|--------|
| `id` | PK |
| `user_id` | FK → users |
| `product_id` | Catalog id from Qdrant / ProductSummary |
| `subject` | Snapshot title |
| `unit_price` | Snapshot; may be null |
| `image_url` | Snapshot; nullable |
| `category_name` | Snapshot |
| `variant_label` | Nullable string, e.g. `Color: Red · Size: M` |
| `quantity` | Integer ≥ 1 |
| `created_at`, `updated_at` | |

**Uniqueness:** `(user_id, product_id, variant_label)` — adding the same line again increments `quantity`.

Store “no variant” as empty string `""` (not SQL NULL) so the unique constraint matches reliably in SQLite.

### `orders`

| Field | Notes |
|-------|--------|
| `id` | PK |
| `user_id` | FK → users |
| `status` | Set to `pending` on create (only value this phase) |
| `recipient_name` | Required |
| `phone` | Required |
| `address` | Required |
| `note` | Optional |
| `total_amount` | Sum of line snapshots (qty × unit_price); null prices handled per rules below |
| `created_at` | |

### `order_items`

Immutable copy of cart line snapshots at checkout time: `order_id`, `product_id`, `subject`, `unit_price`, `image_url`, `category_name`, `variant_label`, `quantity`.

## API (all JWT-required)

| Method | Path | Behavior |
|--------|------|----------|
| `GET` | `/api/cart` | Items + `item_count` (sum of quantities) + `subtotal` |
| `POST` | `/api/cart/items` | Upsert/increment; body = product snapshot + `quantity` + optional `variant_label` |
| `PATCH` | `/api/cart/items/{id}` | Update `quantity` (≥ 1); reject `< 1` with `400` (delete only via DELETE) |
| `DELETE` | `/api/cart/items/{id}` | Remove line (owner-only) |
| `POST` | `/api/orders` | Checkout body: `recipient_name`, `phone`, `address`, `note?`; build order from cart; clear cart; empty cart → `400` |

### Authorization

- Every cart/order row scoped to the authenticated user.
- Cross-user access → `404` or `403` (prefer `404` for item ids to avoid leakage).

### Pricing rules

- Persist `unit_price` from the add-to-cart request snapshot (product price or selected variant price).
- Adding with `unit_price = null` is allowed; UI shows “Price on request”.
- Checkout is blocked if any cart line lacks a numeric `unit_price` (UI disables submit + clear message; API also returns `400`).
- `subtotal` / `total_amount` sum only lines with numeric prices; if any null price exists, treat cart as not checkout-ready.

## Frontend UX

### Header

- Cart icon + badge = sum of `quantity` from `GET /api/cart`.
- Opens a Sheet from the side opposite the session sidebar, respecting `DirectionProvider` (LTR/RTL).

### Cart Sheet

1. Line list: thumbnail, title, variant label, unit price, quantity stepper, remove.
2. Subtotal.
3. **Checkout** advances to an in-Sheet form step (same Sheet, second step).
4. Form fields: recipient name, phone, address, optional note → submit → success toast, close Sheet, badge → 0.
5. Empty cart: short empty state; Checkout hidden/disabled.

### Add to cart entry points

- **ProductSidebar:** Primary “Add to cart”. If product has variants, user must select one first (variants become selectable; today they are display-only). Use selected variant’s price and a stable `variant_label` string; if no variants, use product price and null/empty label.
- **Chat product cards:** Quick “Add to cart”. If the product has variants, open ProductSidebar for variant selection instead of adding blindly.

### Client state

- `CartProvider` on the dashboard/chat layout: initial `GET /api/cart`, refresh after add/patch/delete/checkout.
- New helpers in `frontend/lib/api.ts`.

## Files to touch (expected)

| Area | Change |
|------|--------|
| `backend/app/models/` | `CartItem`, `Order`, `OrderItem` (+ exports) |
| `backend/app/schemas/` | Pydantic request/response models |
| `backend/app/api/cart.py`, `orders.py` | Routers |
| `backend/app/main.py` | Register routers; ensure tables created |
| `frontend/components/cart/*` | Badge, Sheet, checkout form step |
| `frontend/components/chat/ProductSidebar.tsx` | Variant select + Add to cart |
| `frontend/components/chat/MessageList.tsx` (or product card) | Quick add / open sidebar for variants |
| Chat header (e.g. `chat/page.tsx` or header component) | Cart trigger |
| Dashboard/chat layout | `CartProvider` |
| `frontend/lib/api.ts` | Cart/order client API |

## Error handling

| Case | Behavior |
|------|----------|
| No JWT | `401` like existing APIs |
| Empty cart checkout | Button disabled; API `400` |
| `PATCH` quantity `< 1` | `400` |
| Null prices in cart | Add allowed; checkout blocked |
| Network failure on mutate | Toast error; keep previous cart state |
| Successful order | Toast + close Sheet + empty cart |

## Success criteria

- Add from ProductSidebar (with and without variants) and from chat cards (with variant gate).
- Badge and Sheet stay in sync with the server.
- Quantity change and delete work.
- Checkout creates a `pending` order, persists form fields and line snapshots, clears the cart.
- User A cannot read or mutate User B’s cart/orders.

## Test plan (minimum)

- API: add → get → patch → delete; checkout empty vs non-empty; null-price checkout rejected; two-user isolation.
- Manual UI: add from sidebar and card, edit qty, checkout form, empty state, badge updates.

## Out of scope follow-ups (later)

- “My orders” page
- Payment
- Guest cart merge on login
- Chat/LLM tool calling the same cart API
- Admin order inbox
