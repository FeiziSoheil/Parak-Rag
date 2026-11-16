# Chat commerce ordering (Approach 1 — intent + actions on existing cart/orders)

**Date:** 2026-11-16  
**Status:** Draft for review  
**Project:** PARAK — Intelligent Shopping Assistant  
**Depends on:** `docs/superpowers/specs/2026-11-16-chat-cart-orders-design.md` (server cart + pending orders UI)

## Goal

Let logged-in users add items to the cart and complete checkout **through chat** (text and the same path after voice STT): multi-turn collection of recipient name, phone, address, optional note, then place a `pending` order **only after explicit confirmation**. Reuse the existing cart/orders SQLite APIs/services; do not invent a parallel order store.

## Decisions locked

| Topic | Choice |
|-------|--------|
| Scope | Full in-chat cart + checkout (not add-only, not buy-without-cart) |
| Confirmation | Explicit yes/confirm before `POST /orders` |
| Product reference | Attached / sidebar / recent assistant cards; if ambiguous, ask |
| Architecture | LLM returns structured commerce **action JSON**; backend executes against cart/order services |
| Checkout UI in chat | Textual dialogue this phase (no new confirm buttons required) |
| Catalog free-text add | Out of scope (no “search whole catalog by name to add” without chat context) |

## Non-goals

- Payment gateway
- Direct single-item order bypassing cart
- Raw LLM tool-calling as the primary control plane
- “My orders” page / admin inbox
- Free catalog name search solely for add-to-cart
- Changing floating cart panel UX (badge refresh only)

## Architecture

```
User message (+ selected_products / sidebar product context)
  → Intent / commerce action detector (LLM → JSON)
  → If commerce action:
       resolve product refs from session context
       run cart/order service functions
       update session.checkout_state
       compose assistant reply (result-driven; optional light phrasing)
  → Else:
       existing RAG path (product_search / store / faq / chitchat)
  → Response includes message, products?, cart_updated?, order?, checkout_phase?
  → Frontend: show reply; refresh cart if cart_updated
```

LLM never writes to the DB directly. Only validated actions mutate cart/orders.

## Commerce actions

| `action` | Meaning | Server effect |
|----------|---------|----------------|
| `cart_add` | Add to cart | Resolve product → upsert cart line |
| `cart_view` | Show cart | Read cart → summarize in reply |
| `cart_update` | Change qty / remove | PATCH or DELETE cart item |
| `checkout_start` | Begin checkout | `phase=collecting`; ask first missing slot |
| `checkout_fill` | Fill slot(s) from utterance | Merge extracted fields; advance or move to confirm |
| `order_confirm` | Confirm place order | Only if `awaiting_confirm` + checkout_ready → create order, clear cart, `phase=idle` |
| `order_cancel` | Abort checkout | Clear draft fields; `phase=idle` |
| `clarify_product` | Ambiguous product | No mutate; ask which candidate |
| *(existing intents)* | product_search, store_info, faq, … | Existing RAG pipeline |

Action detector output shape (illustrative):

```json
{
  "action": "cart_add",
  "quantity": 1,
  "product_ref": { "hint": "first" | "this" | null, "product_id": null },
  "slots": {
    "recipient_name": null,
    "phone": null,
    "address": null,
    "note": null
  },
  "confirm": false,
  "cancel": false
}
```

When `checkout_state.phase != idle`, checkout handling takes priority over product search so mid-flow answers (e.g. an address) are not treated as catalog queries.

## Product resolution (`cart_add`)

Candidates, in order:

1. Products attached to the current user message (`selected_products`)
2. Product currently open in Product sidebar (frontend sends id/snapshot with the chat request)
3. Product cards on the latest assistant message in this session that included products

Rules:

- 0 candidates → explain nothing is selected; suggest picking a card/sidebar product
- 1 clear candidate → add (respect quantity default 1)
- Multiple / vague reference (“the first one”, “the blue one”) → `clarify_product` with a short list; do not add
- Product has variants and no variant chosen → ask for variant (or use sidebar selection if present)
- Snapshot prices/images into cart as today’s cart API already does

## Checkout state machine

Stored on `chat_sessions.checkout_state` (JSON text column).

```json
{
  "phase": "idle" | "collecting" | "awaiting_confirm",
  "recipient_name": null,
  "phone": null,
  "address": null,
  "note": null,
  "next_slot": null | "recipient_name" | "phone" | "address" | "note"
}
```

Transitions:

```
idle
  --checkout_start--> collecting (ask recipient_name first, then phone, address; note optional)
collecting
  --checkout_fill--> merge slots; if incomplete ask next_slot; if complete --> awaiting_confirm + order summary
awaiting_confirm
  --order_confirm--> create pending order; clear cart; phase=idle; success message
  --order_cancel--> phase=idle; clear draft
  --checkout_fill (correction)--> update fields; re-summarize or return to collecting if critical field cleared
```

**Confirmation gate:** `order_confirm` is a no-op for order creation unless `phase == awaiting_confirm`. Empty cart or `checkout_ready == false` (null prices) blocks with a clear assistant message.

Pre-confirm summary must include: line items, subtotal, recipient name, phone, address, note (if any).

## Data / API changes

### DB

- Add `chat_sessions.checkout_state` (TEXT/JSON, nullable; treat null as idle)
- Ensure column on startup (same pattern as other SQLite `_ensure_*` helpers)

### Shared services

- Factor cart/order mutations used by HTTP routers into callable service functions so chat can invoke them without HTTP-to-self
- Keep HTTP `/api/cart` and `/api/orders` behavior unchanged for the UI panel

### Chat / voice response extras

Extend chat (and voice-chat) JSON with:

| Field | Type | Purpose |
|-------|------|---------|
| `cart_updated` | bool | Frontend refreshes CartProvider |
| `order` | `{ id, total_amount, status } \| null` | Success toast / copy |
| `checkout_phase` | string \| null | Optional UI hint |

Request extras:

| Field | Purpose |
|-------|---------|
| Existing `selected_products` | Attach context |
| `sidebar_product` (JSON snapshot, optional) | Prefer product open in Product details |

### Intent detection

- Extend or add a commerce-action LLM call (temperature 0, JSON-only) alongside/after current `detect_intent_with_llm`
- Commerce actions set `needs_qdrant_search=false` unless explicitly falling through to search
- Voice: after STT, same `_run_chat_response` path

## Frontend

- After chat/voice success: if `cart_updated`, call `refresh()` on cart context
- If `order` present: success toast (cart panel already empties via refresh)
- When Product sidebar is open, include `sidebar_product` snapshot on send (text + voice paths that already send selected products)
- No required new chat buttons this phase; natural language confirm/cancel is enough

## Error handling

| Case | Behavior |
|------|----------|
| Empty cart + checkout_start | Tell user; stay idle or non-collecting |
| Null-priced lines + confirm | Block; explain |
| confirm when not awaiting_confirm | Do not create order; guide user |
| Ambiguous product | Clarify; no add |
| Missing variant | Ask; no add |
| Cancel mid-collect | Clear draft; idle |
| Cart/order service error | User-visible error; leave state consistent (no partial order) |

## Success criteria

- Clear “add this to cart” updates server cart + badge
- Ambiguous add asks clarification and does not add the wrong item
- “I want to order” walks name → phone → address → summary → order only after explicit confirm
- Cancel aborts with no order row
- Normal product search still works when checkout phase is idle
- Voice follows the same commerce path after transcription
- User A cannot affect User B’s cart/orders

## Test plan (minimum)

- Unit/API: state transitions; confirm rejected outside `awaiting_confirm`; empty cart checkout; null price block; two-user isolation
- Integration: detect action → cart_add → checkout_start → fill slots → confirm creates order and clears cart
- Manual: chat add, clarify, full checkout, cancel, search still works, badge sync

## Follow-ups (later)

- Confirm/Cancel chips under the summary message
- Prefill slots from user profile
- Catalog name search for add
- Payment
