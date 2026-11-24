import json
import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models.message import Message
from app.models.order import Order
from app.schemas.cart import CartItemCreate
from app.schemas.order import OrderCreate
from app.services.checkout_state import (
    begin_collecting,
    clean_pending_add,
    dump_checkout_state,
    fill_slots,
    load_checkout_state,
    mark_idle,
    pending_variant_options,
    ready_to_confirm,
)
from app.services.commerce import (
    CommerceError,
    add_cart_item,
    create_order_from_cart,
    delete_cart_item,
    get_cart_for_user,
    update_cart_item,
)



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


_DIGIT_FOLD = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_ORDINAL_INDEX = {
    "first": 0,
    "1st": 0,
    "1": 0,
    "اولی": 0,
    "اولین": 0,
    "second": 1,
    "2nd": 1,
    "2": 1,
    "دومی": 1,
    "دومین": 1,
    "third": 2,
    "3rd": 2,
    "3": 2,
    "سومی": 2,
    "سومین": 2,
    "fourth": 3,
    "4th": 3,
    "4": 3,
    "چهارمی": 3,
    "چهارمین": 3,
    "fifth": 4,
    "5th": 4,
    "5": 4,
    "پنجمی": 4,
    "پنجمین": 4,
}
_ORDINAL_PATTERNS = (
    (re.compile(r"اولین|اولی"), "first"),
    (re.compile(r"دومین|دومی"), "second"),
    (re.compile(r"سومین|سومی"), "third"),
    (re.compile(r"چهارمین|چهارمی"), "fourth"),
    (re.compile(r"پنجمین|پنجمی"), "fifth"),
    (re.compile(r"\bfirst\b|\b1st\b", re.IGNORECASE), "first"),
    (re.compile(r"\bsecond\b|\b2nd\b", re.IGNORECASE), "second"),
    (re.compile(r"\bthird\b|\b3rd\b", re.IGNORECASE), "third"),
    (re.compile(r"\bfourth\b|\b4th\b", re.IGNORECASE), "fourth"),
    (re.compile(r"\bfifth\b|\b5th\b", re.IGNORECASE), "fifth"),
)
_ORDER_RE = re.compile(
    r"نهایی\s*(?:کن|کنید|بکن)|"
    r"\bfinalize(?:\s+it)?\b|"
    r"سفارش(?:ش|شو)?(?:\s*(?:رو|را))?\s*(?:بده(?:ید)?|بدید|بدین|کنید|کنم|کن|بدم)(?!\w)|"
    r"می\s*خ(?:وا|واه)م\s+سفارش|"
    r"سفارش\s*(?:می\s*دم|میدم)|"
    r"\border\s+(?:the|this|that|it|them)\b|"
    r"\bplace\s+(?:an?\s+)?order\b|"
    r"\bwant\s+to\s+order\b|"
    r"\bcheck\s*out\b",
    re.IGNORECASE,
)
_ADD_RE = re.compile(
    r"به\s*سبد|"
    r"تو(?:ی)?\s*سبد|"
    r"داخل\s*سبد|"
    r"سبد(?:م|مون)?(?:\s+\S+){0,3}\s*(?:اضافه|بذار|بگذار|بریز)|"
    r"(?:اضافه|بذار|بگذار|بریز)(?:\s+\S+){0,4}\s*(?:به\s*)?سبد|"
    r"\badd(?:\s+\S+){0,6}\s+to\s+(?:my\s+)?cart\b",
    re.IGNORECASE,
)
_HISTORY_RE = re.compile(
    r"سفارش(?:ش)?(?:\s*(?:های|ها|هام|هامو|هامون|منو|من|م))(?:\s*(?:من|م))?(?:\s*(?:رو|را))?\s*"
    r"(?:لیست|نشون|نمایش|ببین|کجاست|کجان|کو|وضعیت|پیگیری|سابقه|چی\s*شد|داری|بفرست)"
    r"|سفارش(?:ش)?(?:\s*(?:های|ها|هام|هامو|هامون))"
    r"|سابقه(?:\s*ی)?\s*سفارش"
    r"|تاریخچه(?:\s*ی)?\s*سفارش"
    r"|سفارش(?:\s*های)?\s*قبلی"
    r"|پیگیری\s*سفارش"
    r"|وضعیت\s*سفارش"
    r"|\b(?:show|list|see|view|track|find)\s+(?:my\s+)?orders?\b"
    r"|\bmy\s+orders?\s+(?:history|status)\b"
    r"|\bwhere(?:'s|\s+is)\s+my\s+order\b"
    r"|\border\s+history\b",
    re.IGNORECASE,
)
_SELECTED_RE = re.compile(
    r"محصول(?:ات)?\s*انتخاب|"
    r"انتخاب\s*شده|"
    r"selected\s+products",
    re.IGNORECASE,
)
_DEICTIC_RE = re.compile(r"همین|همون|همینو|همونو|اینو|این\s*یکی")
_ACCEPT_RE = re.compile(r"(?:^|[\s،,.])باشه(?:$|[\s،,.])|می\s*خ(?:وا|واه)م")
_HOWTO_RE = re.compile(r"چطور|چگونه|چجوری|چطوری|how\s+(?:do|can|to)\b", re.IGNORECASE)
_COLOR_ALIASES = {
    "بنفش": ("purple", "violet"),
    "ارغوانی": ("purple", "violet"),
    "یاسی": ("lilac", "purple"),
    "مشکی": ("black",),
    "سیاه": ("black",),
    "سفید": ("white",),
    "قرمز": ("red",),
    "سرخ": ("red",),
    "آبی": ("blue",),
    "ابی": ("blue",),
    "سبز": ("green",),
    "زرد": ("yellow",),
    "صورتی": ("pink",),
    "نارنجی": ("orange",),
    "قهوه ای": ("brown", "coffee"),
    "قهوهای": ("brown", "coffee"),
    "قهوه": ("brown", "coffee"),
    "خاکستری": ("gray", "grey"),
    "طوسی": ("gray", "grey"),
    "طلایی": ("gold",),
    "نقره ای": ("silver",),
    "نقره": ("silver",),
    "کرم": ("cream", "beige"),
    "بژ": ("beige",),
    "سرمه ای": ("navy",),
    "سرمه": ("navy",),
}
_ENGLISH_COLORS = (
    "purple",
    "violet",
    "lilac",
    "black",
    "white",
    "red",
    "blue",
    "green",
    "yellow",
    "pink",
    "orange",
    "brown",
    "gray",
    "grey",
    "navy",
    "beige",
    "cream",
    "gold",
    "silver",
    "coffee",
)
_SIZE_ATTR_RE = re.compile(r"size|سایز|اندازه|(?:^|\s)eu(?:\s|$)")
_ORDINAL_HINTS = {"first", "second", "third", "fourth", "fifth"}


def _fold_text(text: str) -> str:
    return text.replace("\u200c", " ").replace("ي", "ی").replace("ك", "ک").translate(_DIGIT_FOLD)


def _ordinal_index(hint: str) -> int | None:
    if not hint:
        return None
    return _ORDINAL_INDEX.get(hint.strip().lower())


def _ordinal_hint(text: str) -> str | None:
    for pattern, hint in _ORDINAL_PATTERNS:
        if pattern.search(text):
            return hint
    return None


def _extract_size(text: str) -> str | None:
    folded = _fold_text(text)
    persian = re.findall(r"سایز\s*[:：]?\s*(\d{1,3})", folded)
    if persian:
        return persian[-1]
    sizes = re.findall(r"\b(?:size|eu)\s*[:：]?\s*(\d{1,3})", folded, flags=re.IGNORECASE)
    return sizes[-1] if sizes else None


def _color_tokens(color: str) -> list[str]:
    folded = _fold_text(color).lower().strip()
    tokens = [folded] if folded else []
    aliases = _COLOR_ALIASES.get(folded) or _COLOR_ALIASES.get(folded.replace(" ", ""))
    if aliases:
        tokens.extend(alias.lower() for alias in aliases)
    return tokens


def _color_matches(color: str, blob: str) -> bool:
    blob_l = _fold_text(blob).lower()
    return any(
        token and re.search(rf"(?<![\w]){re.escape(token)}(?![\w])", blob_l, re.IGNORECASE)
        for token in _color_tokens(color)
    )


def _explicit_color(text: str) -> str | None:
    folded = _fold_text(text)
    match = re.search(r"رنگ\s*[:：]?\s*([^\s,،·|/]+)", folded)
    if not match:
        match = re.search(r"\bcolou?r\s*[:：]\s*([A-Za-z]+)", folded, re.IGNORECASE)
    if match:
        color = match.group(1).strip(" .:：")
        if color and not color.isdigit() and color.lower() not in {"size", "سایز"}:
            return color.lower()
    lowered = folded.lower()
    names = sorted(_COLOR_ALIASES, key=len, reverse=True) + list(_ENGLISH_COLORS)
    for name in names:
        if re.search(rf"(?<![\w]){re.escape(name)}(?![\w])", lowered, re.IGNORECASE):
            return name.lower()
    return None


def _extract_variant_label(message: str) -> str | None:
    size = _extract_size(message)
    color = _explicit_color(message)
    parts = []
    if color:
        parts.append(f"Color: {color}")
    if size:
        parts.append(f"Size: {size}")
    return " · ".join(parts) if parts else None


def _variant_size(variant: dict) -> str | None:
    for attr in variant.get("attributes") or []:
        if not isinstance(attr, dict):
            continue
        name = _fold_text(str(attr.get("name") or "")).lower()
        value = _fold_text(str(attr.get("value") or ""))
        if _SIZE_ATTR_RE.search(name):
            match = re.search(r"\d{1,3}", value)
            return match.group(0) if match else (value or None)
    return _extract_size(variant_label_of(variant))


def _variant_color(variant: dict) -> str:
    for attr in variant.get("attributes") or []:
        if not isinstance(attr, dict):
            continue
        name = _fold_text(str(attr.get("name") or "")).lower()
        if re.search(r"color|colour|رنگ", name):
            return _fold_text(str(attr.get("value") or "")).lower()
    return ""


def _size_or_color_constrained(needle: str) -> bool:
    folded = _fold_text(needle).strip()
    if re.fullmatch(r"\d{1,3}", folded):
        return True
    return _extract_size(needle) is not None or _explicit_color(needle) is not None


def _filter_variants(variants: list[dict], needle: str) -> list[dict]:
    size = _extract_size(needle)
    if size is None and re.fullmatch(r"\d{1,3}", _fold_text(needle).strip()):
        size = _fold_text(needle).strip()
    color = _explicit_color(needle)
    if size is None and color is None:
        return _match_variants(variants, needle)
    hits = []
    for variant in variants:
        if size is not None and _variant_size(variant) != size:
            continue
        if color is not None:
            blob = f"{_variant_color(variant)} {_fold_text(variant_label_of(variant))}"
            if not _color_matches(color, blob):
                continue
        hits.append(variant)
    return hits


def _take_variant(chosen: dict, variant: dict) -> tuple[str, float | None, str | None]:
    label = variant_label_of(variant)
    price = chosen["price"]
    image = chosen["image_url"]
    if variant.get("price") is not None:
        price = variant.get("price")
    if variant.get("image"):
        image = variant.get("image")
    return label, price, image


def _variant_options(variants: list[dict]) -> list[str]:
    return [label for label in (variant_label_of(variant) for variant in variants) if label]


def _is_choice(text: str, ordinal: str | None, variant_label: str | None) -> bool:
    has_anchor = bool(ordinal) or bool(_DEICTIC_RE.search(text))
    if not has_anchor:
        return False
    if _ACCEPT_RE.search(text):
        return True
    if variant_label:
        return True
    # A short ordinal reply («دومی», or a typo like «همود اولی») still picks a
    # shown card even without an accept word; longer search queries do not.
    return bool(ordinal) and len(text.split()) <= 4


def _variant_reply(text: str) -> bool:
    folded = _fold_text(text).strip().lower()
    if not folded:
        return False
    if not (_extract_size(folded) or _explicit_color(folded) or re.fullmatch(r"\d{1,3}", folded)):
        return False
    allowed = r"رنگ|سایز|اندازه|size|eu|colou?r|لطفا|باشه|همین|همون|اینو|این|رو|را|برای|هم|با"
    color_alt = "|".join(re.escape(name) for name in sorted(_COLOR_ALIASES, key=len, reverse=True))
    english = "|".join(_ENGLISH_COLORS)
    pattern = rf"^(?:(?:{allowed}|{color_alt}|{english}|\d{{1,3}})|[\s·:：,،.|/+\-])+$"
    return re.fullmatch(pattern, folded, flags=re.IGNORECASE) is not None


def _rule_commerce_action(message: str, phase: str = "idle") -> dict | None:
    text = _fold_text(message)
    if _HOWTO_RE.search(text):
        return None
    history = _HISTORY_RE.search(text) is not None
    ordering = _ORDER_RE.search(text) is not None
    adding = _ADD_RE.search(text) is not None
    if phase in ("collecting", "awaiting_confirm", "awaiting_variant") and not ordering and not adding and not history:
        return None
    ordinal = _ordinal_hint(text)
    variant_label = _extract_variant_label(text)
    if ordering:
        action_name = "checkout_start"
    elif adding:
        action_name = "cart_add"
    elif history:
        action_name = "order_history"
    elif phase not in ("collecting", "awaiting_confirm") and _is_choice(text, ordinal, variant_label):
        action_name = "cart_add"
    else:
        return None
    return {
        "action": action_name,
        "quantity": 1,
        "add_all": bool(_SELECTED_RE.search(text)) and _ordinal_index(ordinal or "") is None,
        "product_ref": {"hint": ordinal, "product_id": None, "variant_label": variant_label},
        "confirm": False,
        "cancel": False,
    }


def _enrich_action(action: dict, message: str) -> dict:
    if action["action"] not in ("cart_add", "checkout_start", "clarify_product"):
        return action
    ref = dict(action["product_ref"])
    if not ref.get("hint"):
        hint = _ordinal_hint(_fold_text(message))
        if hint:
            ref["hint"] = hint
    if not ref.get("variant_label"):
        label = _extract_variant_label(message)
        if label:
            ref["variant_label"] = label
    enriched = {**action, "product_ref": ref}
    if enriched["action"] == "clarify_product" and ref.get("hint") in _ORDINAL_HINTS:
        enriched["action"] = "cart_add"
    return enriched


def _snapshot(chosen: dict, label: str, price, image) -> dict:
    return {
        "product_id": chosen["product_id"],
        "subject": chosen["subject"],
        "unit_price": _number(price),
        "image_url": image,
        "category_name": chosen["category_name"],
        "variant_label": label,
    }


_NAME_TOKEN_RE = re.compile(r"[A-Za-z0-9]{3,}|[\u0600-\u06FF]{4,}")
_NAME_STOPWORDS = frozenset(
    _fold_text(word)
    for word in (
        "this", "that", "these", "those", "the", "and", "with", "for", "add", "order",
        "cart", "want", "please", "product", "item", "one", "two", "model", "same",
        "buy", "give", "check", "out", "finalize", "first", "second", "third",
        "fourth", "fifth",
        "این", "همین", "همون", "همو", "همود", "محصول", "کالا", "مدل", "سفارش", "سبد",
        "اضافه", "خرید", "میخوام", "خوام", "لطفا", "برام", "بدید", "کنید", "سایز",
        "اندازه", "رنگی", "نهایی", "دومی", "اولی", "سومی", "دوم", "اول", "سوم",
    )
)


def _name_tokens(text: str) -> list[str]:
    tokens = []
    for match in _NAME_TOKEN_RE.findall(text or ""):
        token = match.lower().strip("·:：,،.|/\\-+")
        if len(token) < 3 or token in _NAME_STOPWORDS:
            continue
        tokens.append(token)
    return tokens


def _named_candidates(pool: list[dict], text: str) -> list[tuple[dict, int]]:
    tokens = set(_name_tokens(_fold_text(text)))
    if not tokens:
        return []
    scored = []
    for item in pool:
        blob = _fold_text(
            " ".join(part for part in (item["subject"], item.get("category_name")) if part)
        ).lower()
        hits = sum(1 for token in tokens if token in blob)
        if hits:
            scored.append((item, hits))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored


def _unique_named_candidate(pool: list[dict], text: str) -> dict | None:
    """The one product whose name/brand matches the message tokens, if unambiguous."""
    scored = _named_candidates(pool, text)
    if len(scored) >= 2 and scored[0][1] == scored[1][1]:
        return None
    return scored[0][0] if scored else None


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
    hint = ref.get("hint")
    hint_text = hint.strip() if isinstance(hint, str) else ""
    ordinal = _ordinal_index(hint_text)
    chosen = None
    named_hit = False
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
    if chosen is None and ordinal is not None:
        if ordinal >= len(pool):
            return ResolveProduct(status="clarify", candidates=pool)
        chosen = pool[ordinal]
    if chosen is None and hint_text and hint_text != "this" and ordinal is None:
        named = _unique_named_candidate(pool, hint_text)
        if named is not None:
            chosen = named
            named_hit = True
    if chosen is None and len(pool) > 1:
        return ResolveProduct(status="clarify", candidates=pool)
    if chosen is None:
        chosen = pool[0]

    label = None
    price = chosen["price"]
    image = chosen["image_url"]
    ref_label = ref.get("variant_label")
    if isinstance(ref_label, str):
        ref_label = ref_label.strip()
    else:
        ref_label = ""
    needles = []
    if ref_label:
        needles.append(ref_label)
    # A hint that already resolved the product by name is not a variant needle.
    if hint_text and ordinal is None and hint_text != "this" and not named_hit:
        needles.append(hint_text)
    for needle in needles:
        matched = _filter_variants(chosen["variants"], needle)
        if len(matched) == 1:
            label, price, image = _take_variant(chosen, matched[0])
            break
        if len(matched) > 1 or _size_or_color_constrained(needle):
            return ResolveProduct(
                status="need_variant",
                candidates=[chosen],
                variant_options=_variant_options(matched),
            )
        if not chosen["variants"] and not named_hit:
            label = needle
            break
    side = _as_candidate(sidebar) if isinstance(sidebar, dict) else None
    if label is None and side and side["product_id"] == chosen["product_id"] and side["selected_variant_label"]:
        label = side["selected_variant_label"]
        if side["price"] is not None:
            price = side["price"]
        if side["image_url"]:
            image = side["image_url"]
    if label is None:
        if chosen["variants"]:
            return ResolveProduct(
                status="need_variant",
                candidates=[chosen],
                variant_options=_variant_options(chosen["variants"]),
            )
        label = ""
    return ResolveProduct(status="selected", product=_snapshot(chosen, label, price, image))


ACTIONS = {
    "cart_add",
    "cart_view",
    "cart_update",
    "order_history",
    "checkout_start",
    "checkout_fill",
    "order_confirm",
    "order_cancel",
    "clarify_product",
    "none",
}
ASK = {
    "en": {
        "recipient_name": "Who should receive this order? Please send the recipient's full name.",
        "phone": "What phone number should we use for delivery?",
        "address": "What is the delivery address?",
    },
    "fa": {
        "recipient_name": "این سفارش برای چه کسی است؟ لطفاً نام و نام خانوادگی گیرنده را بفرستید.",
        "phone": "برای ارسال سفارش، چه شماره تماسی را استفاده کنیم؟",
        "address": "آدرس تحویل سفارش چیست؟",
    },
}
TEXT = {
    "en": {
        "EMPTY_CART": "Your cart is empty. Add a product before checkout.",
        "NOT_READY": "I can place the order only after you review the summary and reply yes.",
        "NULL_PRICE": "I can't place the order yet because a cart item has no price.",
        "NO_PRODUCT": "I don't know which product to add. Open a product in the sidebar or pick one of the cards I showed.",
        "CANCELLED": "Checkout cancelled. Your cart is unchanged.",
        "NOT_IN_CART": "I couldn't find that item in your cart.",
        "CART_EMPTY_VIEW": "Your cart is empty.",
        "CART_HEADER": "Your cart:",
        "PRICE_UNAVAILABLE": "price unavailable",
        "UNAVAILABLE": "unavailable",
        "SUBTOTAL": "Subtotal:",
        "SUMMARY_HEADER": "Please confirm this order:",
        "SUMMARY_RECIPIENT": "Recipient:",
        "SUMMARY_PHONE": "Phone:",
        "SUMMARY_ADDRESS": "Address:",
        "SUMMARY_NOTE": "Note:",
        "SUMMARY_FOOTER": 'Reply "yes" to place the order, or "cancel" to stop.',
        "NO_MATCH_VARIANT": "I couldn't find a matching size or color for {subject}.",
        "WHICH_VARIANT": "Which variant of {subject} should I add?",
        "WHICH_PRODUCT": "Which product should I add?",
        "WHICH_CART_ITEM": "Which cart item should I change?",
        "ADDED_TO_CART": "Added {quantity} × {subject}{variant} to your cart.",
        "REMOVED_FROM_CART": "Removed {subject} from your cart.",
        "UPDATED_QUANTITY": "Updated {subject} to quantity {quantity}.",
        "ORDER_PLACED": "Order #{id} placed. Status: {status}. Total: {total}.",
        "ORDERS_HEADER": "Your orders:",
        "ORDERS_EMPTY": "You haven't placed any orders yet.",
        "ORDER_ITEM_LINE": "{quantity} × {subject}{variant}",
        "UNKNOWN_ACTION": "I couldn't do that.",
        "GENERIC_SUBJECT": "this product",
    },
    "fa": {
        "EMPTY_CART": "سبد خرید شما خالی است. قبل از ثبت سفارش یک محصول اضافه کنید.",
        "NOT_READY": "بعد از مرور خلاصه سفارش و تأیید، می‌توانم سفارش را ثبت کنم.",
        "NULL_PRICE": "هنوز نمی‌توانم سفارش را ثبت کنم چون یکی از اقلام سبد قیمت ندارد.",
        "NO_PRODUCT": "نمی‌دانم کدام محصول را اضافه کنم. محصولی را در پنل کنار باز کنید یا یکی از کارت‌هایی که نشان دادم را انتخاب کنید.",
        "CANCELLED": "فرآیند سفارش لغو شد. سبد خرید شما تغییری نکرده است.",
        "NOT_IN_CART": "چنین آیتمی در سبد خرید شما پیدا نکردم.",
        "CART_EMPTY_VIEW": "سبد خرید شما خالی است.",
        "CART_HEADER": "سبد خرید شما:",
        "PRICE_UNAVAILABLE": "قیمت در دسترس نیست",
        "UNAVAILABLE": "در دسترس نیست",
        "SUBTOTAL": "جمع کل:",
        "SUMMARY_HEADER": "لطفاً این سفارش را تأیید کنید:",
        "SUMMARY_RECIPIENT": "گیرنده:",
        "SUMMARY_PHONE": "شماره تماس:",
        "SUMMARY_ADDRESS": "آدرس:",
        "SUMMARY_NOTE": "یادداشت:",
        "SUMMARY_FOOTER": "برای ثبت سفارش «تایید» و برای لغو «لغو» را بنویسید.",
        "NO_MATCH_VARIANT": "برای {subject} سایز یا رنگی پیدا نکردم.",
        "WHICH_VARIANT": "کدام مدل از {subject} را اضافه کنم؟",
        "WHICH_PRODUCT": "کدام محصول را اضافه کنم؟",
        "WHICH_CART_ITEM": "کدام آیتم سبد را تغییر بدهم؟",
        "ADDED_TO_CART": "{quantity} عدد {subject}{variant} به سبد خرید اضافه شد.",
        "REMOVED_FROM_CART": "«{subject}» از سبد خرید حذف شد.",
        "UPDATED_QUANTITY": "تعداد «{subject}» به {quantity} تغییر کرد.",
        "ORDER_PLACED": "سفارش #{id} ثبت شد. وضعیت: {status}. مبلغ کل: {total}.",
        "ORDERS_HEADER": "سفارش‌های شما:",
        "ORDERS_EMPTY": "هنوز سفارشی ثبت نکرده‌اید.",
        "ORDER_ITEM_LINE": "{quantity} عدد {subject}{variant}",
        "UNKNOWN_ACTION": "متوجه نشدم؛ لطفاً دوباره تلاش کنید.",
        "GENERIC_SUBJECT": "این محصول",
    },
}
ORDER_STATUS_I18N = {
    "en": {"pending": "pending"},
    "fa": {"pending": "در انتظار بررسی"},
}


def _t(key: str, lang: str) -> str:
    return TEXT.get(lang, TEXT["en"]).get(key, TEXT["en"][key])


def _ask(slot: str, lang: str) -> str:
    return ASK.get(lang, ASK["en"]).get(slot, ASK["en"][slot])


@dataclass
class CommerceTurn:
    message: str
    cart_updated: bool
    order: dict | None
    checkout_phase: str


def _slot(value):
    if value is None:
        return None
    text = value.strip() if isinstance(value, str) else str(value).strip()
    return text


def normalize_commerce_action(data: dict | None) -> dict:
    raw = data if isinstance(data, dict) else {}
    action = raw.get("action") or "none"
    if action not in ACTIONS:
        action = "none"
    confirm = bool(raw.get("confirm"))
    cancel = bool(raw.get("cancel"))
    if action == "none" and cancel:
        action = "order_cancel"
    elif action == "none" and confirm:
        action = "order_confirm"
    quantity = raw.get("quantity")
    try:
        quantity = int(quantity) if quantity is not None else 1
    except (TypeError, ValueError):
        quantity = 1
    remove = bool(raw.get("remove"))
    if action == "cart_update" and quantity == 0:
        remove = True
    if quantity < 1 and not remove:
        quantity = 1
    ref = raw.get("product_ref") if isinstance(raw.get("product_ref"), dict) else {}
    product_id = ref.get("product_id")
    try:
        product_id = int(product_id) if product_id is not None else None
    except (TypeError, ValueError):
        product_id = None
    hint = ref.get("hint")
    hint = hint.strip() if isinstance(hint, str) and hint.strip() else None
    variant_label = ref.get("variant_label")
    variant_label = variant_label.strip() if isinstance(variant_label, str) else None
    slots_in = raw.get("slots") if isinstance(raw.get("slots"), dict) else {}
    slots = {key: _slot(slots_in.get(key)) for key in ("recipient_name", "phone", "address", "note")}
    return {
        "action": action,
        "quantity": quantity,
        "remove": remove,
        "product_ref": {"hint": hint, "product_id": product_id, "variant_label": variant_label},
        "slots": slots,
        "confirm": confirm,
        "cancel": cancel,
        "add_all": bool(raw.get("add_all")),
    }


def load_recent_product_cards(db: Session, session_id: int) -> list[dict]:
    rows = (
        db.query(Message)
        .filter(Message.session_id == session_id, Message.role == "assistant", Message.products.isnot(None))
        .order_by(Message.created_at.desc(), Message.id.desc())
        .all()
    )
    for row in rows:
        if not row.products or not str(row.products).strip():
            continue
        try:
            parsed = json.loads(row.products)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, list) and any(isinstance(item, dict) and item.get("product_id") is not None for item in parsed):
            return [item for item in parsed if isinstance(item, dict)]
    return []


def _save_state(db, session, state: dict) -> None:
    session.checkout_state = dump_checkout_state(state)
    db.commit()


def _money(value) -> str:
    return f"${float(value):.2f}"


def _lang_of(state: dict | None) -> str:
    lang = (state or {}).get("lang")
    return lang if lang in ("en", "fa") else "en"


def format_cart(cart, lang: str = "en") -> str:
    if not cart.items:
        return _t("CART_EMPTY_VIEW", lang)
    lines = [_t("CART_HEADER", lang)]
    for item in cart.items:
        variant = f" ({item.variant_label})" if item.variant_label else ""
        price = _money(item.unit_price) if item.unit_price is not None else _t("PRICE_UNAVAILABLE", lang)
        lines.append(f"- {item.subject}{variant} ×{item.quantity} — {price}")
    subtotal = _money(cart.subtotal) if cart.subtotal is not None else _t("UNAVAILABLE", lang)
    lines.append(f"{_t('SUBTOTAL', lang)} {subtotal}")
    return "\n".join(lines)


def format_order_summary(cart, state: dict) -> str:
    lang = _lang_of(state)
    lines = [_t("SUMMARY_HEADER", lang)]
    for item in cart.items:
        variant = f" ({item.variant_label})" if item.variant_label else ""
        price = _money(item.unit_price) if item.unit_price is not None else _t("PRICE_UNAVAILABLE", lang)
        lines.append(f"- {item.subject}{variant} ×{item.quantity} — {price}")
    subtotal = _money(cart.subtotal) if cart.subtotal is not None else _t("UNAVAILABLE", lang)
    lines.append(f"{_t('SUBTOTAL', lang)} {subtotal}")
    lines.append(f"{_t('SUMMARY_RECIPIENT', lang)} {state.get('recipient_name')}")
    lines.append(f"{_t('SUMMARY_PHONE', lang)} {state.get('phone')}")
    lines.append(f"{_t('SUMMARY_ADDRESS', lang)} {state.get('address')}")
    if state.get("note"):
        lines.append(f"{_t('SUMMARY_NOTE', lang)} {state.get('note')}")
    lines.append(_t("SUMMARY_FOOTER", lang))
    return "\n".join(lines)


def _resolve_message(resolved: ResolveProduct, lang: str = "en") -> str:
    if resolved.status == "none":
        return _t("NO_PRODUCT", lang)
    if resolved.status == "need_variant":
        subject = resolved.candidates[0]["subject"] if resolved.candidates else _t("GENERIC_SUBJECT", lang)
        if not resolved.variant_options:
            return _t("NO_MATCH_VARIANT", lang).format(subject=subject)
        lines = [_t("WHICH_VARIANT", lang).format(subject=subject)]
        for index, label in enumerate(resolved.variant_options, start=1):
            lines.append(f"{index}. {label}")
        return "\n".join(lines)
    lines = [_t("WHICH_PRODUCT", lang)]
    for index, candidate in enumerate(resolved.candidates, start=1):
        price = candidate.get("price")
        suffix = f" — {_money(price)}" if isinstance(price, (int, float)) else ""
        lines.append(f"{index}. {candidate.get('subject')}{suffix}")
    return "\n".join(lines)


def _turn(message: str, state: dict, *, cart_updated: bool = False, order: dict | None = None) -> CommerceTurn:
    return CommerceTurn(message=message, cart_updated=cart_updated, order=order, checkout_phase=state["phase"])


def format_orders(orders, lang: str = "en") -> str:
    if not orders:
        return _t("ORDERS_EMPTY", lang)
    status_i18n = ORDER_STATUS_I18N.get(lang, ORDER_STATUS_I18N["en"])
    lines = [_t("ORDERS_HEADER", lang)]
    for order in orders:
        status = status_i18n.get(order.status, order.status)
        lines.append(f"#{order.id} · {status} · {_money(order.total_amount)}")
        for item in order.items:
            variant = f" ({item.variant_label})" if item.variant_label else ""
            lines.append(f"  {_t('ORDER_ITEM_LINE', lang).format(quantity=item.quantity, subject=item.subject, variant=variant)}")
    return "\n".join(lines)


def _targets_product(ref: dict | None) -> bool:
    if not isinstance(ref, dict):
        return False
    if ref.get("product_id") is not None:
        return True
    if isinstance(ref.get("variant_label"), str) and ref["variant_label"].strip():
        return True
    return bool(isinstance(ref.get("hint"), str) and ref["hint"].strip())


def _specific_product_ref(ref: dict | None) -> bool:
    if not isinstance(ref, dict):
        return False
    if ref.get("product_id") is not None:
        return True
    hint = ref.get("hint") if isinstance(ref.get("hint"), str) else ""
    if _ordinal_index(hint) is not None:
        return True
    # A name/brand hint points at one specific product, not "everything shown".
    stripped = hint.strip()
    return bool(stripped) and stripped.lower() != "this"


def _added_line(quantity: int, snap: dict, lang: str = "en") -> str:
    variant = f" ({snap['variant_label']})" if snap["variant_label"] else ""
    return _t("ADDED_TO_CART", lang).format(quantity=quantity, subject=snap["subject"], variant=variant)


def _remember_pending(db, session, state, action, resolved) -> dict:
    if resolved.status != "need_variant" or not resolved.candidates:
        return state
    product_id = resolved.candidates[0].get("product_id")
    if product_id is None:
        return state
    name = action.get("action")
    if name not in ("cart_add", "checkout_start"):
        name = "cart_add"
    hint = (action.get("product_ref") or {}).get("hint")
    state = dict(state)
    state["pending_add"] = {
        "product_id": int(product_id),
        "action": name,
        "hint": hint,
        "variant_options": list(resolved.variant_options),
    }
    _save_state(db, session, state)
    return load_checkout_state(session.checkout_state)


def clear_pending_add(db, session) -> None:
    state = load_checkout_state(session.checkout_state)
    if not state.get("pending_add"):
        return
    state.pop("pending_add", None)
    _save_state(db, session, state)


def _clear_pending(db, session, state) -> dict:
    if not state.get("pending_add"):
        return state
    state = {key: value for key, value in state.items() if key != "pending_add"}
    _save_state(db, session, state)
    return load_checkout_state(session.checkout_state)


def _write_cart_snap(db, user_id, action, snap: dict) -> None:
    add_cart_item(
        db,
        user_id,
        CartItemCreate(
            product_id=snap["product_id"],
            subject=snap["subject"],
            unit_price=snap["unit_price"],
            image_url=snap["image_url"],
            category_name=snap["category_name"],
            variant_label=snap["variant_label"],
            quantity=action["quantity"],
        ),
    )


def _add_selected_product(db, user_id, session, action, attached, sidebar, recent, state, user_message=None):
    lang = _lang_of(state)
    ref = action["product_ref"]
    attached_cards = [card for card in (_as_candidate(item) for item in (attached or [])) if card]
    use_all = bool(attached_cards) and (
        action.get("add_all")
        or (len(attached_cards) > 1 and not _specific_product_ref(ref) and not (ref.get("variant_label") or "").strip())
    )
    if use_all:
        resolved_rows = []
        for card in attached_cards:
            one_ref = {"hint": None, "product_id": card["product_id"], "variant_label": ref.get("variant_label")}
            resolved = resolve_product_for_cart([card], None, [], one_ref)
            if resolved.status != "selected" or not resolved.product:
                if resolved.status == "need_variant":
                    state = _remember_pending(db, session, state, action, resolved)
                return _turn(_resolve_message(resolved, lang), state), [], state
            resolved_rows.append(resolved)
        for resolved in resolved_rows:
            _write_cart_snap(db, user_id, action, resolved.product)
        db.refresh(session)
        state = _clear_pending(db, session, load_checkout_state(session.checkout_state))
        return None, [resolved.product for resolved in resolved_rows], state

    resolved = resolve_product_for_cart(attached, sidebar, recent, ref)
    if resolved.status == "clarify" and user_message:
        # The user may name the product (brand/model) instead of picking a
        # numbered card; retry once with the named card pinned.
        named = _unique_named_candidate(_pool(attached or [], sidebar, recent or []), user_message)
        if named is not None:
            resolved = resolve_product_for_cart(
                attached,
                sidebar,
                recent,
                {**ref, "product_id": named["product_id"], "hint": None},
            )
    if resolved.status != "selected" or not resolved.product:
        if resolved.status == "need_variant":
            state = _remember_pending(db, session, state, action, resolved)
        return _turn(_resolve_message(resolved, lang), state), [], state
    _write_cart_snap(db, user_id, action, resolved.product)
    db.refresh(session)
    state = _clear_pending(db, session, load_checkout_state(session.checkout_state))
    return None, [resolved.product], state


_PERSIAN_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")


def detect_reply_language(text: str | None, current: str = "en") -> str:
    """Pick the reply language from the user's message.

    Persian/Arabic script wins outright; otherwise Latin-script messages keep the
    session language so mixed numbers ("09142895825") do not flip it to English
    mid-checkout when the user started in Persian.
    """
    folded = (text or "").strip()
    if not folded:
        return current if current in ("en", "fa") else "en"
    if _PERSIAN_RE.search(folded):
        return "fa"
    if re.search(r"[A-Za-z]", folded):
        return "en"
    return current if current in ("en", "fa") else "en"


def execute_commerce_action(
    db: Session,
    user_id: int,
    session,
    action: dict,
    *,
    attached_products: list[dict],
    sidebar_product: dict | None,
    recent_products: list[dict] | None = None,
    user_message: str | None = None,
) -> CommerceTurn:
    action = normalize_commerce_action(action)
    state = load_checkout_state(session.checkout_state)
    state["lang"] = detect_reply_language(user_message, state.get("lang") or "en")
    pending = clean_pending_add(state.get("pending_add"))
    options = pending_variant_options(state)
    if pending and action["action"] in ("cart_add", "checkout_start"):
        ref = dict(action["product_ref"])
        hint = ref.get("hint")
        ordinal = _ordinal_index(hint) if isinstance(hint, str) else None
        has_label = bool((ref.get("variant_label") or "").strip())
        in_variant_clarify = bool(options)
        if in_variant_clarify:
            # A variant question is open: replies naming an option or a position
            # belong to the pending product, not a new card.
            bind = ref.get("product_id") is None and (ordinal is not None or has_label)
        else:
            bind = ref.get("product_id") is None and not _specific_product_ref(ref)
        if bind:
            ref["product_id"] = pending["product_id"]
            resumed = action["action"]
            if resumed == "cart_add" and pending["action"] == "checkout_start":
                resumed = "checkout_start"
            if ordinal is not None:
                # An ordinal in a variant question picks the Nth shown option,
                # not the Nth product card.
                label = _variant_option_label_from_ref(ref, options)
                if label is not None and not has_label:
                    ref["variant_label"] = label
                ref["hint"] = None
            action = {**action, "action": resumed, "product_ref": ref}
    if recent_products is None:
        recent_products = load_recent_product_cards(db, session.id)
    name = action["action"]

    lang = _lang_of(state)
    if name == "cart_view":
        return _turn(format_cart(get_cart_for_user(db, user_id), lang), state)

    if name == "order_history":
        orders = (
            db.query(Order)
            .filter(Order.user_id == user_id)
            .order_by(Order.id.desc())
            .limit(20)
            .all()
        )
        return _turn(format_orders(orders, lang), state)

    if name == "clarify_product":
        resolved = resolve_product_for_cart(
            attached_products,
            sidebar_product,
            recent_products,
            action["product_ref"],
        )
        if resolved.status == "selected" and resolved.product:
            return _turn(_t("WHICH_PRODUCT", lang) + f"\n1. {resolved.product['subject']}", state)
        return _turn(_resolve_message(resolved, lang), state)

    if name == "cart_add":
        early, snaps, state = _add_selected_product(
            db,
            user_id,
            session,
            action,
            attached_products,
            sidebar_product,
            recent_products,
            state,
            user_message=user_message,
        )
        if early:
            return early
        if not snaps:
            return _turn(_t("NO_PRODUCT", lang), state)
        message = "\n".join(_added_line(action["quantity"], snap, lang) for snap in snaps)
        if state["phase"] == "awaiting_confirm":
            message += "\n\n" + format_order_summary(get_cart_for_user(db, user_id), state)
        return _turn(message, state, cart_updated=True)

    if name == "cart_update":
        cart = get_cart_for_user(db, user_id)
        ref = action["product_ref"]
        items = list(cart.items)
        if ref.get("product_id") is not None:
            matched = [item for item in items if item.product_id == ref["product_id"]]
        elif len(items) == 1:
            matched = items
        else:
            matched = []
        if len(matched) == 0:
            message = _t("NOT_IN_CART", lang) if items else _t("EMPTY_CART", lang)
            if len(items) > 1 and ref.get("product_id") is None:
                message = _t("WHICH_CART_ITEM", lang) + "\n" + "\n".join(
                    f"- {item.subject}" + (f" ({item.variant_label})" if item.variant_label else "")
                    for item in items
                )
            return _turn(message, state)
        if len(matched) > 1:
            message = _t("WHICH_CART_ITEM", lang) + "\n" + "\n".join(f"- {item.subject}" for item in matched)
            return _turn(message, state)
        target = matched[0]
        if action["remove"]:
            delete_cart_item(db, user_id, target.id)
            message = _t("REMOVED_FROM_CART", lang).format(subject=target.subject)
        else:
            update_cart_item(db, user_id, target.id, action["quantity"])
            message = _t("UPDATED_QUANTITY", lang).format(subject=target.subject, quantity=action["quantity"])
        db.refresh(session)
        state = load_checkout_state(session.checkout_state)
        return _turn(message, state, cart_updated=True)

    if name in ("checkout_start", "checkout_fill"):
        added = None
        if name == "checkout_start":
            attached_cards = [card for card in (_as_candidate(item) for item in attached_products) if card]
            pool = _pool(attached_products, sidebar_product, recent_products)
            named = _unique_named_candidate(pool, user_message or "")
            ref = action["product_ref"]
            if named is not None and ref.get("product_id") is None and not _specific_product_ref(ref):
                # The user named the product (brand/model); pin it instead of
                # forcing a numbered choice.
                ref["product_id"] = named["product_id"]
                action = {**action, "product_ref": ref}
            should_add = bool(
                _targets_product(action["product_ref"])
                or action.get("add_all")
                or attached_cards
                or named is not None
                or len(pool) == 1
            )
            if should_add:
                early, snaps, state = _add_selected_product(
                    db,
                    user_id,
                    session,
                    action,
                    attached_products,
                    sidebar_product,
                    recent_products,
                    state,
                    user_message=user_message,
                )
                if early:
                    return early
                if snaps:
                    added = "\n".join(_added_line(action["quantity"], snap) for snap in snaps)
        if state["phase"] == "idle" and not get_cart_for_user(db, user_id).items:
            return _turn(_t("EMPTY_CART", lang), state)
        state = begin_collecting(state) if name == "checkout_start" else fill_slots(state, action["slots"])
        _save_state(db, session, state)
        if state["phase"] == "awaiting_confirm":
            message = format_order_summary(get_cart_for_user(db, user_id), state)
        else:
            message = _ask(state["next_slot"], _lang_of(state))
        if added:
            message = added + "\n\n" + message
        return _turn(message, state, cart_updated=added is not None)

    if name == "order_confirm":
        if state["phase"] != "awaiting_confirm":
            return _turn(_t("NOT_READY", lang), state)
        if any(value not in (None, "") for value in action["slots"].values()):
            state = fill_slots(state, action["slots"])
            _save_state(db, session, state)
            if state["phase"] != "awaiting_confirm":
                return _turn(_ask(state["next_slot"], _lang_of(state)), state)
        if not ready_to_confirm(state):
            return _turn(_t("NOT_READY", lang), state)
        cart = get_cart_for_user(db, user_id)
        if not cart.items:
            return _turn(_t("EMPTY_CART", lang), state)
        if not cart.checkout_ready:
            return _turn(_t("NULL_PRICE", lang), state)
        idle = mark_idle()
        idle["lang"] = lang
        session.checkout_state = dump_checkout_state(idle)
        try:
            order = create_order_from_cart(
                db,
                user_id,
                OrderCreate(
                    recipient_name=state["recipient_name"],
                    phone=state["phone"],
                    address=state["address"],
                    note=state.get("note"),
                ),
            )
        except CommerceError as err:
            db.rollback()
            db.refresh(session)
            kept = load_checkout_state(session.checkout_state)
            return _turn(err.detail, kept)
        payload = {"id": order.id, "total_amount": float(order.total_amount), "status": order.status}
        total = f"${order.total_amount:.2f}"
        message = _t("ORDER_PLACED", lang).format(
            id=order.id,
            status=ORDER_STATUS_I18N.get(lang, ORDER_STATUS_I18N["en"]).get(order.status, order.status),
            total=total,
        )
        return _turn(message, idle, cart_updated=True, order=payload)

    if name == "order_cancel":
        state = mark_idle()
        _save_state(db, session, state)
        return _turn(_t("CANCELLED", lang), state)

    return _turn(_t("UNKNOWN_ACTION", lang), state)


def _detector_prompt(message: str, phase: str) -> str:
    return f"""You classify a shopping-assistant utterance into one commerce action. Respond with ONLY a JSON object.

Current checkout phase: "{phase}"
User message: {json.dumps(message)}

The user may write in any language.
If phase is collecting or awaiting_confirm, treat the message as checkout (checkout_fill, order_confirm, or order_cancel) unless the user is clearly starting a new product search.
If they are clearly starting a new product search, return action "none".
Do not search the catalog yourself. Do not invent product ids.

JSON schema:
{{
  "action": "cart_add" | "cart_view" | "cart_update" | "order_history" | "checkout_start" | "checkout_fill" | "order_confirm" | "order_cancel" | "clarify_product" | "none",
  "quantity": 1,
  "remove": false,
  "product_ref": {{"hint": "first" | "second" | "third" | "fourth" | "fifth" | "this" | "a product name or brand mentioned by the user" | null, "product_id": null, "variant_label": null}},
  "slots": {{"recipient_name": null, "phone": null, "address": null, "note": null}},
  "confirm": false,
  "cancel": false
}}

Rules:
- cart_add: user wants the current product or shown cards added, including Persian «به سبد اضافه کن». Put a color or size in product_ref.variant_label when they name one (سایز ۴۰ / size 40 → "Size: 40"). quantity defaults to 1. When they name a product or brand instead of a number («همین IMICE رو به سبد اضافه کن», "add the Logitech mouse"), put that name or brand into product_ref.hint.
- Ordinals pick one shown card: اولی/first → "first", دومی/second → "second", سومی/third → "third", four and five the same way. «این دومی رو سفارش بده» is checkout_start with hint "second", not a product search.
- cart_view: user asks what is in the cart.
- order_history: user asks about their past or previous orders, order status, or tracking (سفارش‌هام / سفارش‌های من / سفارش‌های قبلی / پیگیری سفارش / my orders / order history / track my order). Return this even during checkout when the user asks about previous orders; it is different from starting a new order.
- cart_update: user changes a quantity. remove true when they want the line deleted. product_ref.product_id stays null unless the message contains an id.
- checkout_start: user wants to order, check out, or place the order (سفارش بده / سفارش بدهید / میخوام سفارش بدم / سفارش کن / نهایی کن) and checkout has not started. Keep the ordinal hint when they name a shown card, and put a product name or brand they mention into product_ref.hint («همین IMICE رو برام سفارش بده» → hint "IMICE").
- cart_add also covers choosing a shown card: «همین اولی باشه», «همون», «اینو میخوام», with an optional color and size (رنگ بنفش سایز ۴۰). That is not a new product search.
- checkout_fill: user is giving recipient_name, phone, address, or note. Copy only the values they actually gave.
- order_confirm: user explicitly agrees to place the order (yes, confirm, place it, بله, تایید). Set confirm true. Do not confirm just because they asked to start an order.
- order_cancel: user aborts checkout. Set cancel true.
- clarify_product: user refers to a product but not one specific card and gives no ordinal.
- none: greeting, product search, store question, FAQ, or anything that is not a cart or checkout action.
"""


def _llm_complete(prompt: str) -> str:
    from langchain_core.messages import HumanMessage
    from langchain_openai import ChatOpenAI

    from app.config import AVALAI_API_KEY
    from app.services.rag import _avalai_chat_kwargs

    if not AVALAI_API_KEY:
        return ""
    llm = ChatOpenAI(**_avalai_chat_kwargs(temperature=0, max_tokens=300))
    response = llm.invoke([HumanMessage(content=prompt)])
    content = response.content if hasattr(response, "content") else str(response)
    return content or ""


def _extract_first_json_object(text: str) -> str | None:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for index, char in enumerate(text[start:], start=start):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


_BARE_ORDINAL_RE = re.compile(
    r"^(?:first|1st|second|2nd|third|3rd|fourth|4th|fifth|5th|\d{1,2}|اولی|اولین|دومی|دومین|سومی|سومین|چهارمی|چهارمین|پنجمی|پنجمین)$",
    re.IGNORECASE,
)


def _variant_option_label_from_ref(ref: dict, options: list[str]) -> str | None:
    """Pick the Nth shown variant option when the reply is a bare ordinal/number.

    Returns the exact listed label, or None when the ref does not point at a
    listed option by position (e.g. it already carries a color/size label).
    """
    if not options:
        return None
    hint = ref.get("hint") if isinstance(ref, dict) else None
    if not isinstance(hint, str) or not hint.strip():
        return None
    index = _ordinal_index(hint)
    if index is None or index >= len(options):
        return None
    return options[index]


def _pending_variant_action(text: str) -> dict | None:
    if not _variant_reply(text):
        return None
    label = _extract_variant_label(text)
    if label is None:
        folded = _fold_text(text).strip()
        if re.fullmatch(r"\d{1,3}", folded):
            label = f"Size: {folded}"
        else:
            color = _explicit_color(folded)
            numbers = re.findall(r"(?<!\d)(\d{1,3})(?!\d)", folded)
            parts = []
            if color:
                parts.append(f"Color: {color}")
            if numbers:
                parts.append(f"Size: {numbers[-1]}")
            label = " · ".join(parts) or None
    return {
        "action": "cart_add",
        "quantity": 1,
        "product_ref": {"hint": None, "product_id": None, "variant_label": label},
        "confirm": False,
        "cancel": False,
    }


def _variant_options_prompt_block(options: list[str]) -> str:
    if not options:
        return ""
    lines = [f"{index}. {option}" for index, option in enumerate(options, start=1)]
    return "The variants of the pending product are:\n" + "\n".join(lines) + "\n"


_VARIANT_REPLY_PROMPT = """You classify the user's reply about product VARIANTS (color, size, ...) for one pending product. Respond with ONLY a JSON object.

{variant_block}User message: {message}

Classify:
- variant: the reply names or clearly points to one of the listed variants. Put the full variant label exactly as listed into product_ref.variant_label. Ordinals or numbers refer to the numbered list (اولی/first/1 → first listed, دومی/second/2 → second listed, and so on). If they mix an ordinal with a color/size, still use the exact listed label that matches best; a Persian color word (بنفش, مشکی, ...) or size (سایز ۴۰) must be matched against the listed labels.
- reject: the reply is a question, a refusal, a new instruction (order now, cancel, add another product), or names a variant that is not listed.
- none: anything else (greeting, unrelated text).

JSON schema:
{{"choice": "variant" | "reject" | "none", "variant_label": null, "hint": null}}
"""


def _variant_reply_via_llm(text: str, options: list[str], *, complete=None) -> dict | None:
    """Ask the LLM to match the reply to one of the shown variant options.

    Returns a cart_add action with a concrete variant_label, or None when the
    reply is not a variant selection (caller falls through to the main detector).
    """
    if not options:
        return None
    prompt = _VARIANT_REPLY_PROMPT.format(
        variant_block=_variant_options_prompt_block(options),
        message=json.dumps(text),
    )
    raw_text = _llm_complete(prompt) if complete is None else complete(prompt)
    json_str = _extract_first_json_object(raw_text or "")
    if not json_str:
        return None
    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    if parsed.get("choice") != "variant":
        return None
    label = parsed.get("variant_label")
    if not isinstance(label, str) or not label.strip():
        return None
    label = label.strip()
    if label not in options:
        lowered = {option.lower(): option for option in options}
        label = lowered.get(label.lower(), label)
    return {
        "action": "cart_add",
        "quantity": 1,
        "product_ref": {"hint": None, "product_id": None, "variant_label": label},
        "confirm": False,
        "cancel": False,
    }


def detect_commerce_action(message: str | None, checkout_phase: str, *, complete=None) -> dict:
    if not message or not str(message).strip():
        return normalize_commerce_action(None)
    text = str(message).strip()
    known_phases = ("idle", "collecting", "awaiting_confirm", "awaiting_variant")
    raw_phase = checkout_phase if checkout_phase in known_phases else "idle"
    ruled = _rule_commerce_action(text, raw_phase)
    if ruled is not None:
        return normalize_commerce_action(ruled)
    if raw_phase == "awaiting_variant":
        pending_action = _pending_variant_action(text)
        if pending_action is not None:
            return normalize_commerce_action(pending_action)
        # Bare ordinal («دومی», "2", "second") answering a variant question:
        # hint only — execute_commerce_action maps it to the Nth shown option.
        if _BARE_ORDINAL_RE.match(_fold_text(text).strip()):
            ordinal = _ordinal_hint(text) or _fold_text(text).strip().lower()
            return normalize_commerce_action(
                {
                    "action": "cart_add",
                    "quantity": 1,
                    "product_ref": {"hint": ordinal, "product_id": None, "variant_label": None},
                    "confirm": False,
                    "cancel": False,
                }
            )
    phase = raw_phase if raw_phase in ("idle", "collecting", "awaiting_confirm") else "idle"
    prompt = _detector_prompt(text, phase)
    raw_text = _llm_complete(prompt) if complete is None else complete(prompt)
    json_str = _extract_first_json_object(raw_text or "")
    data = None
    if json_str:
        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            data = parsed
    return _enrich_action(normalize_commerce_action(data), text)


def detect_variant_reply_action(
    message: str | None,
    variant_options: list[str],
    *,
    complete=None,
) -> dict | None:
    """Resolve a reply to a pending variant question via the LLM.

    Returns a cart_add action with a concrete variant_label when the reply
    matches one of the listed options; None otherwise (caller falls back to
    the normal commerce detection).
    """
    if not message or not str(message).strip():
        return None
    return _variant_reply_via_llm(str(message).strip(), list(variant_options or []), complete=complete)
