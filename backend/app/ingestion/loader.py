"""Load product JSONs from data/AE_Data and extract normalized product records."""
import json
import re
from pathlib import Path
from typing import Any

RESULT_PATH = ("details", "aliexpress_ds_product_get_response", "result")


def _get_nested(data: dict, path: tuple[str, ...], default: Any = None) -> Any:
    current = data
    for key in path:
        current = current.get(key) if isinstance(current, dict) else None
        if current is None:
            return default
    return current


def _strip_html(html: str) -> str:
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    return " ".join(text.split())


def _extract_variants(sku_list: list) -> list[dict]:
    """Build normalized variants from ae_item_sku_info_d_t_o list. Each variant: image, price, attributes [{name, value}]."""
    out: list[dict] = []
    for sku in sku_list:
        if not isinstance(sku, dict):
            continue
        price_raw = sku.get("offer_sale_price") or sku.get("sku_price")
        try:
            price_val = float(price_raw) if price_raw is not None else None
        except (TypeError, ValueError):
            price_val = None
        prop_dtos = sku.get("ae_sku_property_dtos") or {}
        prop_list = (prop_dtos.get("ae_sku_property_d_t_o") or []) if isinstance(prop_dtos, dict) else []
        image_url = None
        attributes: list[dict] = []
        for p in prop_list:
            if not isinstance(p, dict):
                continue
            name = p.get("sku_property_name") or p.get("property_value_definition_name")
            value = p.get("sku_property_value") or p.get("property_value_definition_name")
            if name or value:
                attributes.append({"name": str(name or ""), "value": str(value or "")})
            if image_url is None and p.get("sku_image"):
                image_url = (p.get("sku_image") or "").strip() or None
        out.append({
            "image": image_url,
            "price": price_val,
            "attributes": attributes,
        })
    return out


def _build_context_text(
    base: dict,
    props: list[dict] | None,
    category_id: int | None,
    category_name: str | None,
    price: str | float | None,
    subject: str,
    variants: list[dict] | None = None,
) -> str:
    parts = [f"## {subject}"]
    if price is not None:
        parts.append(f"**Price:** {price}")
    if category_name:
        parts.append(f"**Category:** {category_name}")
    if category_id:
        parts.append(f"**Category ID:** {category_id}")
    if props:
        parts.append("**Specifications:**")
        for p in props:
            name = p.get("attr_name") or p.get("attr_value")
            val = p.get("attr_value") or p.get("attr_name")
            if name and val and str(name).lower() not in ("choice", "cn"):
                parts.append(f"- {name}: {val}")
    detail = _get_nested(base, ("detail",))
    if detail:
        parts.append("**Description:**")
        parts.append(_strip_html(detail)[:2000])
    if variants:
        parts.append("**Variants:**")
        for v in variants:
            price_val = v.get("price")
            price_str = f"${price_val:.2f}" if price_val is not None and isinstance(price_val, (int, float)) else "N/A"
            attr_parts = [f"Price: {price_str}"]
            for attr in v.get("attributes") or []:
                name = attr.get("name") or ""
                value = attr.get("value") or ""
                if name or value:
                    attr_parts.append(f"{name}: {value}".strip() or "")
            parts.append(" | ".join(p for p in attr_parts if p))
    return "\n".join(parts)


def extract_one_product(item: dict) -> dict | None:
    """Extract one product from a raw JSON item (path: details.aliexpress_ds_product_get_response.result)."""
    result = _get_nested(item, RESULT_PATH)
    if not result or not isinstance(result, dict):
        return None
    base = result.get("ae_item_base_info_dto") or {}
    product_id = base.get("product_id")
    if product_id is None:
        return None
    subject = (base.get("subject") or "").strip() or "Unknown product"
    props_dto = result.get("ae_item_properties") or {}
    props = props_dto.get("ae_item_property")
    if not isinstance(props, list):
        props = []
    category_id = base.get("category_id")
    category_name = None
    product_node = item.get("product") or {}
    cats = product_node.get("categories") or {}
    if isinstance(cats, dict):
        vortem_m = cats.get("vortem_cat_m")
        vortem_l1 = cats.get("vortem_cat_l1")
        if isinstance(vortem_m, dict) and vortem_m.get("name"):
            category_name = vortem_m["name"]
        elif isinstance(vortem_l1, dict) and vortem_l1.get("name"):
            category_name = vortem_l1["name"]
    price = product_node.get("targetSalePrice") or product_node.get("targetOriginalPrice")
    sku_dtos = result.get("ae_item_sku_info_dtos") or {}
    sku_list = (sku_dtos.get("ae_item_sku_info_d_t_o") or []) if isinstance(sku_dtos, dict) else []
    variants = _extract_variants(sku_list)
    if price is None and sku_list:
        first_sku = sku_list[0]
        if isinstance(first_sku, dict):
            price = first_sku.get("offer_sale_price") or first_sku.get("sku_price")
    if price is not None and not isinstance(price, (int, float)):
        try:
            price = float(price)
        except (TypeError, ValueError):
            price = None
    context_text = _build_context_text(base, props, category_id, category_name, price, subject, variants=variants)
    image_urls_str = _get_nested(result, ("ae_multimedia_info_dto", "image_urls"))
    image_urls = [u.strip() for u in (image_urls_str or "").split(";") if u.strip()]
    # Fallback for RAG main data (normalized_output): product has itemMainPic but ae_multimedia_info_dto.image_urls may be empty
    if not image_urls and product_node:
        main_pic = product_node.get("itemMainPic")
        if main_pic and isinstance(main_pic, str) and main_pic.strip():
            image_urls = [main_pic.strip()]
    return {
        "product_id": product_id,
        "subject": subject,
        "context_text": context_text,
        "price": price,
        "category_id": category_id,
        "category_name": category_name or "",
        "image_urls": image_urls,
        "variants": variants,
    }


def load_all_products(data_dir: str) -> list[dict]:
    """Load all JSON files from data_dir and return list of extracted products (idempotent-ready: product_id per record)."""
    path = Path(data_dir)
    if not path.is_dir():
        return []
    products: list[dict] = []
    seen_ids: set[int] = set()
    for f in path.glob("*.json"):
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(raw, list):
            raw = [raw]
        for item in raw:
            if not isinstance(item, dict):
                continue
            prod = extract_one_product(item)
            if prod and prod["product_id"] not in seen_ids:
                seen_ids.add(prod["product_id"])
                products.append(prod)
    return products
