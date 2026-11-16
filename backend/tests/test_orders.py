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
