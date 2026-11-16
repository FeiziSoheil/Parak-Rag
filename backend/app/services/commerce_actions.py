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
