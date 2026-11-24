import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import cart as cart_api
from app.api import chat as chat_api
from app.api import orders as orders_api
from app.core.database import get_db
from app.models.cart import CartItem
from app.models.message import Message
from app.models.order import Order
from app.models.session import ChatSession
from app.services.checkout_state import dump_checkout_state, empty_state, load_checkout_state
from app.services.commerce_actions import normalize_commerce_action

MUG = {
    "product_id": 101,
    "subject": "Blue Mug",
    "price": 12.5,
    "image_url": "https://example.com/mug.jpg",
    "category_name": "Home",
    "variants": [],
}


@pytest.fixture()
def chat_client(db_session):
    app = FastAPI()
    app.include_router(chat_api.router, prefix="/api")
    app.include_router(cart_api.router, prefix="/api")
    app.include_router(orders_api.router, prefix="/api")

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def _session(db, user) -> ChatSession:
    row = ChatSession(user_id=user.id, title="New Chat")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _patch_quiet(monkeypatch):
    monkeypatch.setattr(chat_api, "detect_emotion_with_llm", lambda *args, **kwargs: "neutral")

    async def no_audio(text, lang=None):
        return None

    monkeypatch.setattr(chat_api, "text_to_speech_to_bytes", no_audio)


def test_idle_none_action_still_searches(chat_client, db_session, user_a, auth_header_a, monkeypatch):
    session = _session(db_session, user_a)
    calls = {"search": 0, "rag": 0}
    _patch_quiet(monkeypatch)
    monkeypatch.setattr(
        chat_api,
        "detect_commerce_action",
        lambda message, phase: normalize_commerce_action({"action": "none"}),
    )
    monkeypatch.setattr(
        chat_api,
        "detect_intent_with_llm",
        lambda message: {"needs_qdrant_search": True, "intent_type": "product_search", "confidence": 1.0},
    )

    def fake_enhanced(**kwargs):
        calls["search"] += 1
        return {"results": []}

    def fake_rag(*args, **kwargs):
        calls["rag"] += 1
        return "Here are some mugs"

    monkeypatch.setattr(chat_api, "enhanced_search_with_llm", fake_enhanced)
    monkeypatch.setattr(chat_api, "get_query_vector", lambda *args, **kwargs: [0.0])
    monkeypatch.setattr(chat_api, "search_store", lambda *args, **kwargs: [])
    monkeypatch.setattr(chat_api, "search_faq", lambda *args, **kwargs: [])
    monkeypatch.setattr(chat_api, "build_combined_context", lambda *args, **kwargs: "ctx")
    monkeypatch.setattr(chat_api, "products_from_search_results", lambda results: [])
    monkeypatch.setattr(chat_api, "is_broad_products_query", lambda text: True)
    monkeypatch.setattr(chat_api, "run_rag_response", fake_rag)

    response = chat_client.post(
        "/api/chat",
        data={"session_id": str(session.id), "message": "show me mugs"},
        headers=auth_header_a,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["message"] == "Here are some mugs"
    assert body["cart_updated"] is False
    assert body["order"] is None
    assert body["checkout_phase"] == "idle"
    assert calls == {"search": 1, "rag": 1}


def test_chat_add_then_checkout_confirm(chat_client, db_session, user_a, user_b, auth_header_a, monkeypatch):
    session = _session(db_session, user_a)
    _session(db_session, user_b)
    script = [
        {"action": "cart_add", "quantity": 1},
        {"action": "checkout_start"},
        {"action": "checkout_fill", "slots": {"recipient_name": "Ada", "phone": "+98912", "address": "Tehran"}},
        {"action": "order_confirm"},
    ]

    def fake_detect(message, phase):
        return normalize_commerce_action(script.pop(0))

    rag_calls = {"n": 0}
    _patch_quiet(monkeypatch)
    monkeypatch.setattr(chat_api, "detect_commerce_action", fake_detect)
    monkeypatch.setattr(chat_api, "run_rag_response", lambda *args, **kwargs: rag_calls.__setitem__("n", rag_calls["n"] + 1))

    def post(text, extra=None):
        data = {"session_id": str(session.id), "message": text}
        if extra:
            data.update(extra)
        return chat_client.post("/api/chat", data=data, headers=auth_header_a)

    added = post("add this", {"selected_products": json.dumps([MUG]), "sidebar_product": "not-json"})
    assert added.status_code == 200
    assert added.json()["cart_updated"] is True
    assert added.json()["order"] is None
    assert "Blue Mug" in added.json()["message"]

    started = post("I want to order")
    assert started.json()["checkout_phase"] == "collecting"
    filled = post("Ada, +98912, Tehran")
    assert filled.json()["checkout_phase"] == "awaiting_confirm"
    assert "Please confirm this order:" in filled.json()["message"]
    done = post("yes")
    body = done.json()
    assert body["cart_updated"] is True
    assert body["order"]["status"] == "pending"
    assert body["order"]["total_amount"] == 12.5
    assert body["checkout_phase"] == "idle"
    assert rag_calls["n"] == 0
    assert db_session.query(CartItem).filter(CartItem.user_id == user_a.id).count() == 0
    assert db_session.query(Order).filter(Order.user_id == user_b.id).count() == 0
    assert db_session.query(Order).filter(Order.user_id == user_a.id).count() == 1


def test_collecting_phase_is_passed_and_skips_search(chat_client, db_session, user_a, auth_header_a, monkeypatch):
    session = _session(db_session, user_a)
    state = {**empty_state(), "phase": "collecting", "next_slot": "address", "recipient_name": "Ada", "phone": "+1"}
    session.checkout_state = dump_checkout_state(state)
    db_session.commit()
    seen = {}

    def fake_detect(message, phase):
        seen["phase"] = phase
        seen["message"] = message
        return normalize_commerce_action({"action": "checkout_fill", "slots": {"address": "1 Main St"}})

    _patch_quiet(monkeypatch)
    monkeypatch.setattr(chat_api, "detect_commerce_action", fake_detect)
    monkeypatch.setattr(chat_api, "enhanced_search_with_llm", lambda **kwargs: (_ for _ in ()).throw(AssertionError("search")))
    response = chat_client.post(
        "/api/chat",
        data={"session_id": str(session.id), "message": "1 Main St"},
        headers=auth_header_a,
    )
    assert response.status_code == 200
    assert seen == {"phase": "collecting", "message": "1 Main St"}
    assert response.json()["checkout_phase"] == "awaiting_confirm"
    db_session.refresh(session)
    assert load_checkout_state(session.checkout_state)["address"] == "1 Main St"


def test_voice_uses_same_commerce_path(chat_client, db_session, user_a, auth_header_a, monkeypatch):
    session = _session(db_session, user_a)
    _patch_quiet(monkeypatch)
    monkeypatch.setattr(chat_api, "transcribe_audio", lambda path: "add this mug")
    monkeypatch.setattr(
        chat_api,
        "detect_commerce_action",
        lambda message, phase: normalize_commerce_action({"action": "cart_add", "quantity": 1}),
    )
    response = chat_client.post(
        "/api/voice-chat",
        data={"session_id": str(session.id), "selected_products": json.dumps([MUG])},
        files={"voice": ("clip.webm", b"fake-audio", "audio/webm")},
        headers=auth_header_a,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["transcribed_text"] == "add this mug"
    assert body["cart_updated"] is True
    assert "Blue Mug" in body["message"]
    assert db_session.query(CartItem).filter(CartItem.user_id == user_a.id).count() == 1


def test_image_turn_skips_commerce(chat_client, db_session, user_a, auth_header_a, monkeypatch):
    session = _session(db_session, user_a)
    _patch_quiet(monkeypatch)

    def forbid_commerce(*args, **kwargs):
        raise AssertionError("commerce detector")

    monkeypatch.setattr(chat_api, "detect_commerce_action", forbid_commerce)
    monkeypatch.setattr(chat_api, "run_embed_and_search", lambda *args, **kwargs: [])
    monkeypatch.setattr(chat_api, "get_query_vector", lambda *args, **kwargs: [0.0])
    monkeypatch.setattr(chat_api, "search_store", lambda *args, **kwargs: [])
    monkeypatch.setattr(chat_api, "search_faq", lambda *args, **kwargs: [])
    monkeypatch.setattr(chat_api, "build_combined_context", lambda *args, **kwargs: "ctx")
    monkeypatch.setattr(chat_api, "products_from_search_results", lambda results: [])
    monkeypatch.setattr(chat_api, "is_broad_products_query", lambda text: True)
    monkeypatch.setattr(chat_api, "run_rag_response", lambda *args, **kwargs: "similar products")
    response = chat_client.post(
        "/api/chat",
        data={"session_id": str(session.id), "message": ""},
        files={"image": ("x.jpg", b"\xff\xd8\xff", "image/jpeg")},
        headers=auth_header_a,
    )
    assert response.status_code == 200
    assert response.json()["message"] == "similar products"
    assert response.json()["cart_updated"] is False


def _block_rag(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("fell through to rag")

    monkeypatch.setattr(chat_api, "detect_intent_with_llm", fail)
    monkeypatch.setattr(chat_api, "enhanced_search_with_llm", fail)
    monkeypatch.setattr(chat_api, "run_rag_response", fail)
    monkeypatch.setattr(
        "app.services.commerce_actions._llm_complete",
        lambda prompt: '{"action":"none"}',
    )


def test_chat_order_second_shown_card_does_not_search(chat_client, db_session, user_a, auth_header_a, monkeypatch):
    session = _session(db_session, user_a)
    shoes = [
        {"product_id": 11, "subject": "Trail Shoe", "price": 30, "image_url": None, "category_name": "Shoes", "variants": []},
        {"product_id": 22, "subject": "Court Shoe", "price": 40, "image_url": None, "category_name": "Shoes", "variants": []},
        {"product_id": 33, "subject": "Road Shoe", "price": 50, "image_url": None, "category_name": "Shoes", "variants": []},
    ]
    db_session.add(Message(session_id=session.id, role="assistant", content="shoes", products=json.dumps(shoes)))
    db_session.commit()
    _patch_quiet(monkeypatch)
    _block_rag(monkeypatch)
    response = chat_client.post(
        "/api/chat",
        data={"session_id": str(session.id), "message": "این دومی رو سفارش بده"},
        headers=auth_header_a,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cart_updated"] is True
    assert body["order"] is None
    assert body["checkout_phase"] == "collecting"
    assert "Court Shoe" in body["message"]
    item = db_session.query(CartItem).filter(CartItem.user_id == user_a.id).one()
    assert item.product_id == 22
    assert db_session.query(Order).count() == 0


def test_chat_add_first_size_filters_variants(chat_client, db_session, user_a, auth_header_a, monkeypatch):
    session = _session(db_session, user_a)
    variants = []
    for color in ("PURPLE", "BLACK"):
        for size in ("39", "40"):
            variants.append(
                {
                    "price": 18,
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
            "price": 18,
            "image_url": None,
            "category_name": "Shoes",
            "variants": variants,
        },
        {
            "product_id": 78,
            "subject": "Other Shoe",
            "price": 19,
            "image_url": None,
            "category_name": "Shoes",
            "variants": [],
        },
    ]
    db_session.add(Message(session_id=session.id, role="assistant", content="shoes", products=json.dumps(shoes)))
    db_session.commit()
    _patch_quiet(monkeypatch)
    _block_rag(monkeypatch)
    response = chat_client.post(
        "/api/chat",
        data={"session_id": str(session.id), "message": "همین اولی رو با سایز 40 به سبدم اضافه کن"},
        headers=auth_header_a,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cart_updated"] is False
    assert body["order"] is None
    assert "Size: 39" not in body["message"]
    assert body["message"].count("Size: 40") == 2
    assert "PURPLE" in body["message"] and "BLACK" in body["message"]
    assert db_session.query(CartItem).count() == 0


def _shoe_cards():
    variants = []
    for color in ("PURPLE", "BLACK", "WHITE"):
        for size in ("39", "40", "41"):
            variants.append(
                {
                    "price": 36.17,
                    "attributes": [
                        {"name": "Color", "value": color},
                        {"name": "Size", "value": size},
                    ],
                }
            )
    return [
        {
            "product_id": 501,
            "subject": "Mens Supportive Running Shoes",
            "price": 36.17,
            "image_url": None,
            "category_name": "Shoes",
            "variants": variants,
        },
        {
            "product_id": 502,
            "subject": "Other Sneaker",
            "price": 20,
            "image_url": None,
            "category_name": "Shoes",
            "variants": [],
        },
    ]


def test_chat_screenshot_phrase_adds_first_purple_size(chat_client, db_session, user_a, auth_header_a, monkeypatch):
    session = _session(db_session, user_a)
    db_session.add(
        Message(session_id=session.id, role="assistant", content="shoes", products=json.dumps(_shoe_cards()))
    )
    db_session.commit()
    _patch_quiet(monkeypatch)
    _block_rag(monkeypatch)
    response = chat_client.post(
        "/api/chat",
        data={"session_id": str(session.id), "message": "همین اولی باشه رنگ بنفش سایز ۴۰"},
        headers=auth_header_a,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cart_updated"] is True
    assert body["products"] == []
    assert body["order"] is None
    assert body["checkout_phase"] == "idle"
    assert "ثبت شد" not in body["message"]
    assert "1 عدد Mens Supportive Running Shoes (Color: PURPLE · Size: 40)" in body["message"]
    assert "به سبد خرید اضافه شد" in body["message"]
    item = db_session.query(CartItem).filter(CartItem.user_id == user_a.id).one()
    assert item.product_id == 501
    assert item.variant_label == "Color: PURPLE · Size: 40"
    assert item.quantity == 1
    assert db_session.query(Order).count() == 0


def test_chat_selected_products_order_checks_out_without_placing(chat_client, db_session, user_a, auth_header_a, monkeypatch):
    session = _session(db_session, user_a)
    cap = {**MUG, "product_id": 202, "subject": "Red Cap", "price": 9}
    _patch_quiet(monkeypatch)
    _block_rag(monkeypatch)
    response = chat_client.post(
        "/api/chat",
        data={
            "session_id": str(session.id),
            "message": "با محصولات انتخاب‌شده سفارش بده",
            "selected_products": json.dumps([MUG, cap]),
        },
        headers=auth_header_a,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cart_updated"] is True
    assert body["products"] == []
    assert body["order"] is None
    assert body["checkout_phase"] == "collecting"
    assert "ثبت شد" not in body["message"]
    assert "Blue Mug" in body["message"] and "Red Cap" in body["message"]
    assert "Who should receive this order?" in body["message"]
    items = db_session.query(CartItem).filter(CartItem.user_id == user_a.id).all()
    assert {item.product_id for item in items} == {101, 202}
    assert db_session.query(Order).count() == 0


def test_chat_variant_ordinal_reply_adds_nth_listed_option(chat_client, db_session, user_a, auth_header_a, monkeypatch):
    """Screenshot regression: variant list «1. Color: WHITE / 2. Color: black» + bare «دومی»
    must add the pending product's second listed variant — no RAG, no hallucinated add."""
    session = _session(db_session, user_a)
    db_session.add(
        Message(session_id=session.id, role="assistant", content="mouse", products=json.dumps(_shoe_cards()))
    )
    db_session.commit()
    _patch_quiet(monkeypatch)
    _block_rag(monkeypatch)

    def post(text):
        return chat_client.post(
            "/api/chat",
            data={"session_id": str(session.id), "message": text},
            headers=auth_header_a,
        )

    asked = post("همین اولی باشه")
    assert asked.status_code == 200
    assert asked.json()["cart_updated"] is False
    assert "کدام مدل از" in asked.json()["message"]
    db_session.refresh(session)
    pending = load_checkout_state(session.checkout_state)["pending_add"]
    assert pending["product_id"] == 501
    assert pending["variant_options"], "variant options must be stored for the pending product"

    added = post("دومی")
    assert added.status_code == 200
    body = added.json()
    assert body["cart_updated"] is True
    assert body["order"] is None
    assert "ثبت شد" not in body["message"]
    item = db_session.query(CartItem).filter(CartItem.user_id == user_a.id).one()
    assert item.product_id == 501
    # Second listed option of product 501: PURPLE 40 (PURPLE39, PURPLE40, ...)
    assert item.variant_label == "Color: PURPLE · Size: 40"
    assert item.quantity == 1
    assert db_session.query(Order).count() == 0
    db_session.refresh(session)
    assert load_checkout_state(session.checkout_state).get("pending_add") is None


def test_chat_variant_clarify_followup_adds_named_color(chat_client, db_session, user_a, auth_header_a, monkeypatch):
    session = _session(db_session, user_a)
    db_session.add(
        Message(session_id=session.id, role="assistant", content="shoes", products=json.dumps(_shoe_cards()))
    )
    db_session.commit()
    _patch_quiet(monkeypatch)
    _block_rag(monkeypatch)

    def post(text):
        return chat_client.post(
            "/api/chat",
            data={"session_id": str(session.id), "message": text},
            headers=auth_header_a,
        )

    asked = post("همین اولی باشه")
    assert asked.status_code == 200
    assert asked.json()["cart_updated"] is False
    assert asked.json()["products"] == []
    assert "کدام مدل از" in asked.json()["message"]
    assert db_session.query(CartItem).count() == 0
    db_session.refresh(session)
    pending = load_checkout_state(session.checkout_state)["pending_add"]
    assert pending["product_id"] == 501
    assert pending["action"] == "cart_add"

    added = post("رنگ بنفش سایز ۴۰")
    assert added.status_code == 200
    body = added.json()
    assert body["cart_updated"] is True
    assert body["products"] == []
    assert body["order"] is None
    assert "Color: PURPLE · Size: 40" in body["message"]
    assert "ثبت شد" not in body["message"]
    item = db_session.query(CartItem).filter(CartItem.user_id == user_a.id).one()
    assert item.product_id == 501
    assert item.variant_label == "Color: PURPLE · Size: 40"
    assert db_session.query(Order).count() == 0
