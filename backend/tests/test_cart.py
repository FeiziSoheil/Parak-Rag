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
