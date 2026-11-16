from dataclasses import dataclass, field


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
