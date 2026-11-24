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


def test_list_orders_returns_own_newest_first(client, auth_header_a, auth_header_b):
    # User A places two orders; user B has none.
    client.post("/api/cart/items", json=SAMPLE, headers=auth_header_a)
    first = client.post("/api/orders", json=CHECKOUT, headers=auth_header_a).json()
    client.post("/api/cart/items", json=SAMPLE, headers=auth_header_a)
    second = client.post("/api/orders", json=CHECKOUT, headers=auth_header_a).json()

    r = client.get("/api/orders", headers=auth_header_a)
    assert r.status_code == 200
    orders = r.json()
    assert [o["id"] for o in orders] == [second["id"], first["id"]]
    assert all(o["recipient_name"] == "Alice" for o in orders)
    assert orders[0]["items"][0]["subject"] == "Blue Mug"

    # User B never sees user A's orders.
    r_b = client.get("/api/orders", headers=auth_header_b)
    assert r_b.status_code == 200
    assert r_b.json() == []

    # Anonymous requests are rejected.
    assert client.get("/api/orders").status_code == 401
