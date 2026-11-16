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
