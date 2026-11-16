import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import cart as cart_api
from app.api import chat as chat_api
from app.api import orders as orders_api
from app.core.database import get_db
from app.models.cart import CartItem
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
