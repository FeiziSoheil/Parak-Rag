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
