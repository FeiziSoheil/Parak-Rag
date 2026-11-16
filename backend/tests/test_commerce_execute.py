import json

from app.models.cart import CartItem
from app.models.message import Message
from app.models.order import Order
from app.models.session import ChatSession
from app.services.checkout_state import load_checkout_state
from app.services.commerce import CommerceError
from app.services.commerce_actions import (
    detect_commerce_action,
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
        {"action": "cart_add", "product_ref": {"hint": "this"}},
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


def _shown_shoes():
    return [
        {"product_id": 11, "subject": "Trail Shoe", "price": 30.0, "image_url": None, "category_name": "Shoes", "variants": []},
        {"product_id": 22, "subject": "Court Shoe", "price": 40.0, "image_url": None, "category_name": "Shoes", "variants": []},
        {"product_id": 33, "subject": "Road Shoe", "price": 50.0, "image_url": None, "category_name": "Shoes", "variants": []},
    ]


def test_order_second_shown_product_starts_checkout_without_placing(db_session, user_a):
    session = _session(db_session, user_a)
    action = detect_commerce_action(
        "این دومی رو سفارش بده",
        "idle",
        complete=lambda prompt: '{"action":"none"}',
    )
    turn = _run(db_session, user_a, session, action, recent=_shown_shoes())
    assert turn.order is None
    assert turn.cart_updated is True
    assert turn.checkout_phase == "collecting"
    assert "Court Shoe" in turn.message
    assert "Who should receive this order?" in turn.message
    item = db_session.query(CartItem).filter(CartItem.user_id == user_a.id).one()
    assert item.product_id == 22
    blocked = _run(db_session, user_a, session, {"action": "order_confirm"})
    assert blocked.order is None
    assert blocked.message == "I can place the order only after you review the summary and reply yes."
    assert db_session.query(Order).count() == 0


def test_add_first_size_40_clarifies_only_that_size(db_session, user_a):
    variants = []
    for color in ("PURPLE", "BLACK", "WHITE"):
        for size in ("36", "39", "40", "41", "45"):
            variants.append(
                {
                    "price": 18.0,
                    "attributes": [
                        {"name": "Color", "value": color},
                        {"name": "Size", "value": size},
                    ],
                }
            )
    shoes = [
        {
            "product_id": 77,
            "subject": "Trail Shoe",
            "price": 18.0,
            "image_url": None,
            "category_name": "Shoes",
            "variants": variants,
        },
        {
            "product_id": 78,
            "subject": "Other Shoe",
            "price": 19.0,
            "image_url": None,
            "category_name": "Shoes",
            "variants": [],
        },
    ]
    session = _session(db_session, user_a)
    action = detect_commerce_action(
        "همین اولی رو با سایز 40 به سبدم اضافه کن",
        "idle",
        complete=lambda prompt: '{"action":"none"}',
    )
    turn = _run(db_session, user_a, session, action, recent=shoes)
    assert turn.cart_updated is False
    assert turn.order is None
    assert "Which variant of Trail Shoe should I add?" in turn.message
    assert "Size: 40" in turn.message
    assert "Size: 36" not in turn.message
    assert "Size: 39" not in turn.message
    assert "Size: 41" not in turn.message
    assert "Size: 45" not in turn.message
    assert turn.message.count("Size: 40") == 3
    assert db_session.query(CartItem).filter(CartItem.user_id == user_a.id).count() == 0
    assert db_session.query(Order).count() == 0
