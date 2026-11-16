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


def test_multiple_products_clarify_for_this_blue_or_missing_hint():
    for hint in ("this", "blue", None):
        resolved = resolve_product_for_cart([], None, [MUG, CUP], {"hint": hint, "product_id": None})
        assert resolved.status == "clarify"
        assert resolved.product is None
        assert [c["product_id"] for c in resolved.candidates] == [101, 303]


def test_ordinal_hint_selects_shown_card():
    first = resolve_product_for_cart([], None, [MUG, CUP, SHIRT], {"hint": "first", "product_id": None})
    second = resolve_product_for_cart([], None, [MUG, CUP, SHIRT], {"hint": "second", "product_id": None})
    assert first.status == "selected"
    assert first.product["product_id"] == 101
    assert second.status == "selected"
    assert second.product["product_id"] == 303


def _shoe_variants():
    variants = []
    for color in ("PURPLE", "BLACK", "WHITE"):
        for size in ("39", "40", "41"):
            variants.append(
                {
                    "price": 21.0,
                    "image": f"https://example.com/{color}-{size}.jpg",
                    "attributes": [
                        {"name": "Color", "value": color},
                        {"name": "Size", "value": size},
                    ],
                }
            )
    variants.append(
        {
            "price": 19.0,
            "image": None,
            "attributes": [
                {"name": "Color", "value": "RED"},
                {"name": "Size", "value": "140"},
            ],
        }
    )
    return variants


SHOE = {
    "product_id": 404,
    "subject": "Trail Shoe",
    "price": 20.0,
    "image_url": None,
    "category_name": "Shoes",
    "variants": _shoe_variants(),
}


def test_size_constraint_lists_only_matching_variants():
    resolved = resolve_product_for_cart(
        [SHOE],
        None,
        [],
        {"hint": "first", "product_id": None, "variant_label": "size 40"},
    )
    assert resolved.status == "need_variant"
    assert resolved.product is None
    assert len(resolved.variant_options) == 3
    assert resolved.variant_options == [
        "Color: PURPLE · Size: 40",
        "Color: BLACK · Size: 40",
        "Color: WHITE · Size: 40",
    ]


def test_unique_persian_size_selects_that_variant():
    shoe = {
        **SHOE,
        "variants": [
            variant
            for variant in _shoe_variants()
            if not (
                any(attr.get("value") == "40" for attr in variant["attributes"])
                and any(attr.get("value") != "PURPLE" for attr in variant["attributes"] if attr.get("name") == "Color")
            )
        ],
    }
    resolved = resolve_product_for_cart(
        [],
        None,
        [shoe, CUP],
        {"hint": "first", "product_id": None, "variant_label": "سایز ۴۰"},
    )
    assert resolved.status == "selected"
    assert resolved.product["product_id"] == 404
    assert resolved.product["variant_label"] == "Color: PURPLE · Size: 40"
    assert resolved.product["unit_price"] == 21.0


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
