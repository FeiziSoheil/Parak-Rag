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
        user_message=kwargs.get("user_message"),
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


def test_persian_user_gets_persian_checkout_flow(db_session, user_a):
    session = _session(db_session, user_a)
    turn = _run(
        db_session,
        user_a,
        session,
        {"action": "cart_add"},
        attached=[MUG],
        user_message="همین رو به سبد اضافه کن",
    )
    assert "به سبد خرید اضافه شد" in turn.message

    started = _run(db_session, user_a, session, {"action": "checkout_start"}, user_message="سفارش بده")
    assert started.checkout_phase == "collecting"
    assert started.message == "این سفارش برای چه کسی است؟ لطفاً نام و نام خانوادگی گیرنده را بفرستید."

    named = _run(
        db_session,
        user_a,
        session,
        {"action": "checkout_fill", "slots": {"recipient_name": "سهرل فیضی"}},
        user_message="سهرل فیضی",
    )
    assert named.message == "برای ارسال سفارش، چه شماره تماسی را استفاده کنیم؟"

    # Numbers-only follow-up (a phone number) must stay Persian via session lang.
    phone = _run(
        db_session,
        user_a,
        session,
        {"action": "checkout_fill", "slots": {"phone": "09142895825"}},
        user_message="09142895825",
    )
    assert phone.message == "آدرس تحویل سفارش چیست؟"

    address = _run(
        db_session,
        user_a,
        session,
        {"action": "checkout_fill", "slots": {"address": "تهران، ولیعصر"}},
        user_message="تهران، ولیعصر",
    )
    assert address.checkout_phase == "awaiting_confirm"
    assert "لطفاً این سفارش را تأیید کنید:" in address.message
    assert "گیرنده: سهرل فیضی" in address.message
    assert "شماره تماس: 09142895825" in address.message
    assert "آدرس: تهران، ولیعصر" in address.message
    assert "برای ثبت سفارش «تایید»" in address.message

    placed = _run(db_session, user_a, session, {"action": "order_confirm"}, user_message="تایید")
    assert placed.order["status"] == "pending"
    assert f"سفارش #{placed.order['id']} ثبت شد" in placed.message
    assert "وضعیت: در انتظار بررسی" in placed.message
    assert db_session.query(Order).count() == 1
    db_session.refresh(session)
    state = load_checkout_state(session.checkout_state)
    assert state["phase"] == "idle"
    assert state["lang"] == "fa"

    cancelled = _run(db_session, user_a, session, {"action": "order_cancel"}, user_message="لغو")
    assert cancelled.message == "فرآیند سفارش لغو شد. سبد خرید شما تغییری نکرده است."


def test_english_turn_switches_back_and_numbers_only_defaults_english(db_session, user_a):
    session = _session(db_session, user_a)
    fa = _run(db_session, user_a, session, {"action": "cart_view"}, user_message="سبد خریدم رو نشون بده")
    assert fa.message == "سبد خرید شما خالی است."
    en = _run(db_session, user_a, session, {"action": "cart_view"}, user_message="show my cart")
    assert en.message == "Your cart is empty."
    numbers = _run(db_session, user_a, session, {"action": "cart_view"}, user_message="123456")
    assert numbers.message == "Your cart is empty."


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


def test_order_by_product_name_pins_named_card(db_session, user_a):
    """Screenshot regression: «همین IMICE رو برام سفارش بده» with several shown
    cards must add the IMICE product, not answer "cart is empty"."""
    recent = [
        {"product_id": 51, "subject": "adidas Runner", "price": 60.0, "image_url": None, "category_name": "Shoes", "variants": []},
        {"product_id": 52, "subject": "IMICE Gaming Mouse", "price": 15.0, "image_url": None, "category_name": "Mouse", "variants": []},
        {"product_id": 53, "subject": "Logitech Keyboard", "price": 25.0, "image_url": None, "category_name": "Keyboard", "variants": []},
    ]
    session = _session(db_session, user_a)
    action = detect_commerce_action(
        "همین IMICE رو برام سفارش بده",
        "idle",
        complete=lambda prompt: '{"action":"none"}',
    )
    turn = _run(db_session, user_a, session, action, recent=recent, user_message="همین IMICE رو برام سفارش بده")
    assert turn.order is None
    assert "سبد خرید شما خالی است" not in turn.message
    item = db_session.query(CartItem).filter(CartItem.user_id == user_a.id).one()
    assert item.product_id == 52
    assert "IMICE Gaming Mouse" in turn.message


def test_add_by_product_name_resolves_without_clarify(db_session, user_a):
    recent = [
        {"product_id": 61, "subject": "adidas Runner", "price": 60.0, "image_url": None, "category_name": "Shoes", "variants": []},
        {"product_id": 62, "subject": "IMICE Gaming Mouse", "price": 15.0, "image_url": None, "category_name": "Mouse", "variants": []},
    ]
    session = _session(db_session, user_a)
    action = detect_commerce_action(
        "همین IMICE رو به سبد اضافه کن",
        "idle",
        complete=lambda prompt: '{"action":"none"}',
    )
    turn = _run(db_session, user_a, session, action, recent=recent, user_message="همین IMICE رو به سبد اضافه کن")
    assert turn.cart_updated is True
    item = db_session.query(CartItem).filter(CartItem.user_id == user_a.id).one()
    assert item.product_id == 62


def test_add_without_name_or_ordinal_still_clarifies(db_session, user_a):
    recent = [
        {"product_id": 71, "subject": "Trail Shoe", "price": 30.0, "image_url": None, "category_name": "Shoes", "variants": []},
        {"product_id": 72, "subject": "Court Shoe", "price": 40.0, "image_url": None, "category_name": "Shoes", "variants": []},
    ]
    session = _session(db_session, user_a)
    action = detect_commerce_action(
        "همین مدل رو به سبد اضافه کن",
        "idle",
        complete=lambda prompt: '{"action":"none"}',
    )
    turn = _run(db_session, user_a, session, action, recent=recent, user_message="همین مدل رو به سبد اضافه کن")
    assert turn.cart_updated is False
    assert "کدام محصول" in turn.message
    assert db_session.query(CartItem).filter(CartItem.user_id == user_a.id).count() == 0
    assert db_session.query(Order).count() == 0


def test_order_history_action_lists_user_orders(db_session, user_a, user_b):
    from app.models.order import OrderItem

    session = _session(db_session, user_a)

    # Empty history first.
    empty = _run(db_session, user_a, session, {"action": "order_history"})
    assert "haven't placed any orders" in empty.message

    def _make_order(user, subject, price, qty):
        order = Order(
            user_id=user.id,
            status="pending",
            recipient_name="Alice",
            phone="+98912",
            address="Tehran",
            total_amount=price * qty,
        )
        db_session.add(order)
        db_session.flush()
        db_session.add(
            OrderItem(
                order_id=order.id,
                product_id=999,
                subject=subject,
                unit_price=price,
                image_url=None,
                category_name="Home",
                variant_label="Color: Blue",
                quantity=qty,
            )
        )
        db_session.commit()
        db_session.refresh(order)
        return order

    old = _make_order(user_a, "Blue Mug", 10.0, 2)
    new = _make_order(user_a, "IMICE Mouse", 27.5, 1)
    other = _make_order(user_b, "Someone Else Mug", 5.0, 1)

    turn = _run(
        db_session,
        user_a,
        session,
        {"action": "order_history"},
        user_message="سفارش‌هام رو نشون بده",
    )
    lines = turn.message.splitlines()
    # Persian user gets the Persian header; newest order first, with the
    # localized pending status («در انتظار بررسی»).
    assert lines[0] == "سفارش‌های شما:"
    assert lines[1].startswith(f"#{new.id}")
    assert "در انتظار بررسی" in lines[1]
    assert "$27.50" in lines[1]
    assert lines[2].strip() == "1 عدد IMICE Mouse (Color: Blue)"
    assert lines[3].startswith(f"#{old.id}")
    assert "$20.00" in lines[3]
    assert lines[4].strip() == "2 عدد Blue Mug (Color: Blue)"
    # The other user's order is never shown.
    assert "Someone Else Mug" not in turn.message
    assert f"#{other.id}" not in turn.message

    # English turn switches the header back to English.
    en_turn = _run(db_session, user_a, session, {"action": "order_history"}, user_message="show my orders")
    en_lines = en_turn.message.splitlines()
    assert en_lines[0] == "Your orders:"
    assert f"#{new.id}" in en_lines[1]
    assert "1 × IMICE Mouse (Color: Blue)" in en_lines[2]
