"""Chat and sessions API. Chat endpoint accepts multipart/form-data and returns JSON response."""
import asyncio
import base64
import json
import logging
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.config import VOICE_TEMP_DIR
from app.core.database import get_db
from app.models.user import User
from app.models.session import ChatSession
from app.models.message import Message
from app.schemas.chat import SessionResponse, SessionUpdate, MessageOut, MessageSearchResult
from app.services.memory import get_chat_history
from app.services.rag import (
    run_embed_and_search,
    enhanced_search_with_llm,
    filter_search_results_by_min_score,
    build_combined_context,
    run_rag_response,
    is_broad_products_query,
    products_from_search_results,
    reorder_products_by_mention,
    get_query_vector,
    search_store,
    search_faq,
    detect_intent_with_llm,
    detect_language_with_llm,
    detect_emotion_with_llm,
)
from app.services.checkout_state import load_checkout_state, pending_variant_options
from app.services.commerce_actions import (
    clear_pending_add,
    detect_commerce_action,
    detect_variant_reply_action,
    execute_commerce_action,
)
from app.services.stt import transcribe_audio
from app.services.tts import text_to_speech_to_bytes

router = APIRouter()
_executor = ThreadPoolExecutor(max_workers=4)
_logger = logging.getLogger(__name__)


def _llm_error_detail(exc: BaseException) -> str:
    """Human-readable message from AvalAI / OpenAI client errors."""
    from openai import APIConnectionError, APIStatusError, AuthenticationError, RateLimitError

    if isinstance(exc, ValueError):
        return str(exc)
    if isinstance(exc, AuthenticationError):
        return (
            "AvalAI API key is invalid or expired. "
            "Update AVALAI_API_KEY in backend/.env and restart the server."
        )
    if isinstance(exc, RateLimitError):
        return (
            "AvalAI rate limit or credit exhausted. Wait a moment, "
            "or top up at https://ava.al/billing / change AVALAI_MODEL in backend/.env"
        )
    if isinstance(exc, APIConnectionError):
        return "Could not reach AvalAI. Check internet connection or VPN/proxy."
    if isinstance(exc, APIStatusError):
        msg = str(exc)
        body = getattr(exc, "body", None)
        if isinstance(body, dict):
            err = body.get("error")
            if isinstance(err, dict) and err.get("message"):
                msg = str(err["message"])
            elif err:
                msg = str(err)
        code = getattr(exc, "status_code", None)
        prefix = f"AvalAI HTTP {code}: " if code else "AvalAI: "
        return prefix + msg
    return f"AI service error: {exc}"


def _raise_llm_http_error(exc: BaseException) -> None:
    """Map AvalAI/OpenAI client errors to API responses (avoid opaque 500s)."""
    _logger.exception("LLM request failed")
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=_llm_error_detail(exc),
    ) from exc


def _strip_markdown_for_tts(text: str) -> str:
    """Remove common markdown so TTS reads plain text (no 'star star', 'hash', etc.)."""
    t = text.strip()
    if not t:
        return t
    # Remove **bold** and __bold__
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"__([^_]+)__", r"\1", t)
    # Remove *italic* and _italic_
    t = re.sub(r"\*([^*]+)\*", r"\1", t)
    t = re.sub(r"_([^_]+)_", r"\1", t)
    # Remove ## headers
    t = re.sub(r"^#+\s*", "", t, flags=re.MULTILINE)
    # Remove list markers - , *, 1.
    t = re.sub(r"^\s*[-*•]\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"^\s*\d+\.\s+", "", t, flags=re.MULTILINE)
    # Collapse multiple newlines
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip() or text.strip()


def _format_product_context(products: list[dict]) -> str:
    """Format selected products as context prefix for the user message.
    This helps the LLM understand which product(s) the user is referring to.
    """
    if not products:
        return ""
    lines = []
    for p in products:
        parts = []
        subject = p.get("subject") or ""
        if subject:
            parts.append(f"Name: {subject}")
        price = p.get("price")
        if price is not None:
            parts.append(f"Price: {price:.2f}" if isinstance(price, (int, float)) else f"Price: {price}")
        category = p.get("category_name") or ""
        if category:
            parts.append(f"Category: {category}")
        # Include variants if available (for color/size questions)
        variants = p.get("variants")
        if variants and isinstance(variants, list):
            variant_strs = []
            for v in variants[:5]:  # Limit to 5 variants
                if isinstance(v, dict):
                    v_name = v.get("name") or v.get("color") or ""
                    v_price = v.get("price")
                    if v_name:
                        if v_price is not None:
                            variant_strs.append(f"{v_name}: ${v_price:.2f}" if isinstance(v_price, (int, float)) else f"{v_name}: ${v_price}")
                        else:
                            variant_strs.append(v_name)
            if variant_strs:
                parts.append(f"Variants: {', '.join(variant_strs)}")
        if parts:
            lines.append("- " + " | ".join(parts))
    if not lines:
        return ""
    return f"[Selected product(s) context:\n" + "\n".join(lines) + "\n]\n\n"


def _get_last_shown_products(db: Session, session_id: int) -> list[dict]:
    """Get products from the most recent assistant message in this session (title + product_id only, same order as shown)."""
    last_assistant = (
        db.query(Message)
        .filter(Message.session_id == session_id, Message.role == "assistant")
        .order_by(Message.created_at.desc())
        .limit(1)
        .first()
    )
    if not last_assistant or not last_assistant.products:
        return []
    try:
        raw = json.loads(last_assistant.products)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(raw, list):
        return []
    out = []
    for p in raw:
        if not isinstance(p, dict):
            continue
        out.append({
            "subject": p.get("subject") or "",
            "product_id": p.get("product_id"),
        })
    return out


@dataclass
class ChatTurnResult:
    message: str
    products: list
    suggested_emotion: str
    cart_updated: bool = False
    order: dict | None = None
    checkout_phase: str | None = None


def _parse_product_list(raw: str | None) -> list[dict]:
    if not raw or not raw.strip():
        return []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def _parse_product_object(raw: str | None) -> dict | None:
    if not raw or not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _persist_turn(db: Session, session: ChatSession, user_text: str, assistant_text: str, products: list | None) -> None:
    db.add(Message(session_id=session.id, role="user", content=user_text, image_url=None))
    db.add(
        Message(
            session_id=session.id,
            role="assistant",
            content=assistant_text,
            products=json.dumps(products) if products else None,
        )
    )
    if session.title == "New Chat" and user_text:
        session.title = user_text[:100] + ("..." if len(user_text) > 100 else "")
    db.commit()


def _chat_payload(result: ChatTurnResult) -> dict:
    return {
        "message": result.message,
        "products": result.products,
        "suggested_emotion": result.suggested_emotion,
        "cart_updated": result.cart_updated,
        "order": result.order,
        "checkout_phase": result.checkout_phase,
    }


async def _run_chat_response(
    db: Session,
    session: ChatSession,
    user_id: int,
    user_text: str,
    image_bytes: bytes | None = None,
    top_k: int | None = None,
    price_max: float | None = None,
    category: str | None = None,
    attached_products: list[dict] | None = None,
    sidebar_product: dict | None = None,
) -> ChatTurnResult:
    loop = asyncio.get_event_loop()
    attached_products = attached_products or []
    checkout = load_checkout_state(session.checkout_state)
    phase = checkout["phase"]
    detect_phase = "awaiting_variant" if phase == "idle" and checkout.get("pending_add") else phase
    search_text = None if user_text == "(user sent an image)" else (user_text or None)

    if not image_bytes:
        # While a variant question is pending, let the LLM match the reply
        # against the exact options we showed (ordinals, colors, sizes).
        variant_action = None
        options = pending_variant_options(checkout) if detect_phase == "awaiting_variant" else []
        if options:
            variant_action = await loop.run_in_executor(
                _executor,
                lambda text=user_text, opts=list(options): detect_variant_reply_action(text, opts),
            )
        if variant_action is not None:
            action = variant_action
        else:
            action = await loop.run_in_executor(
                _executor,
                lambda text=user_text, current=detect_phase: detect_commerce_action(text, current),
            )
        if action.get("action") == "none" and checkout.get("pending_add"):
            clear_pending_add(db, session)
        if action.get("action") != "none":
            turn = execute_commerce_action(
                db,
                user_id,
                session,
                action,
                attached_products=attached_products,
                sidebar_product=sidebar_product,
                user_message=user_text,
            )
            emotion = await loop.run_in_executor(
                _executor,
                lambda: detect_emotion_with_llm(user_text, turn.message),
            )
            if not emotion:
                emotion = "neutral"
            _persist_turn(db, session, user_text, turn.message, products=None)
            return ChatTurnResult(
                message=turn.message,
                products=[],
                suggested_emotion=emotion,
                cart_updated=turn.cart_updated,
                order=turn.order,
                checkout_phase=turn.checkout_phase,
            )

    intent_type = "product_search"
    if image_bytes:
        do_product_search = True
    else:
        intent_result = await loop.run_in_executor(
            _executor,
            lambda text=search_text: detect_intent_with_llm(text),
        )
        do_product_search = intent_result.get("needs_qdrant_search", False)
        intent_type = intent_result.get("intent_type", "unknown")

    include_products = do_product_search and intent_type not in ("store_info", "faq")
    rag_message = user_text
    if attached_products:
        rag_message = _format_product_context(attached_products) + user_text

    if do_product_search:
        search_results: list[dict] = []
        products: list[dict] = []
        if include_products:
            if image_bytes:
                search_results = await loop.run_in_executor(
                    _executor,
                    lambda text=search_text: run_embed_and_search(
                        text, image_bytes, top_k=top_k, price_max=price_max, category=category
                    ),
                )
            else:
                last_shown = _get_last_shown_products(db, session.id)
                enhanced = await loop.run_in_executor(
                    _executor,
                    lambda text=search_text: enhanced_search_with_llm(
                        user_query=text or "",
                        limit=top_k or 3,
                        price_max=price_max,
                        category=category,
                        last_shown_products=last_shown,
                    ),
                )
                search_results = enhanced["results"]
            if not is_broad_products_query(search_text):
                search_results = filter_search_results_by_min_score(search_results)
            products = products_from_search_results(search_results)
        query_vector = await loop.run_in_executor(
            _executor,
            lambda text=search_text: get_query_vector(text, image_bytes),
        )
        store_results = await loop.run_in_executor(
            _executor,
            lambda vector=query_vector: search_store(vector, top_k=3),
        )
        faq_results = await loop.run_in_executor(
            _executor,
            lambda vector=query_vector: search_faq(vector, top_k=5),
        )
        context = build_combined_context(store_results, faq_results, search_results)
    else:
        context = "No relevant products found."
        products = []

    history = get_chat_history(db, session.id)
    search_by_image = image_bytes is not None
    try:
        full_text = await loop.run_in_executor(
            _executor,
            lambda: run_rag_response(context, history, rag_message, search_by_image=search_by_image),
        )
    except Exception as exc:
        _raise_llm_http_error(exc)

    if products and full_text:
        products = reorder_products_by_mention(full_text, products)

    suggested_emotion = await loop.run_in_executor(
        _executor,
        lambda: detect_emotion_with_llm(user_text, full_text),
    )
    if suggested_emotion is None:
        suggested_emotion = "neutral"

    _persist_turn(db, session, user_text, full_text, products)
    return ChatTurnResult(
        message=full_text,
        products=products,
        suggested_emotion=suggested_emotion,
        cart_updated=False,
        order=None,
        checkout_phase=phase,
    )


# دامنه‌های مجاز برای پروکسی تصویر (جلوگیری از abuse)
ALLOWED_IMAGE_HOSTS = {"ae01.alicdn.com", "alicdn.com", "cdn.shopify.com", "i.ebayimg.com"}


@router.get("/proxy-image")
def proxy_product_image(url: str = Query(..., description="Image URL to proxy")):
    """Fetch image from allowed CDN and stream it. Used so product images load despite CORS/referrer blocking."""
    try:
        parsed = urlparse(url)
        if not parsed.scheme in ("http", "https") or not parsed.netloc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid URL")
        host = parsed.netloc.lower()
        if not any(host == h or host.endswith("." + h) for h in ALLOWED_IMAGE_HOSTS):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="URL host not allowed")
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid URL")
    try:
        r = httpx.get(url, follow_redirects=True, timeout=15.0)
        r.raise_for_status()
        content_type = r.headers.get("content-type") or "image/jpeg"
        return Response(content=r.content, media_type=content_type)
    except httpx.HTTPError:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Failed to fetch image")


# Fixed welcome messages (no LLM call).
WELCOME_DASHBOARD = "Select a chat or create a new one to begin."
WELCOME_NEW_CHAT = "Welcome! I'm here to help. Ask about products, search the catalog, or get answers from our FAQ."


@router.get("/welcome")
async def get_welcome(
    type: str = Query(..., description="dashboard | new_chat"),
    current_user: User = Depends(get_current_user),
):
    """Return a fixed welcome message (dashboard or new chat)."""
    if type not in ("dashboard", "new_chat"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="type must be dashboard or new_chat")
    text = WELCOME_DASHBOARD if type == "dashboard" else WELCOME_NEW_CHAT
    return {"text": text}


@router.post("/detect-intent")
async def detect_intent(
    message: str = Form(..., description="User message to analyze"),
    has_image: bool = Form(False, description="Whether user is sending an image"),
    current_user: User = Depends(get_current_user),
):
    """
    Detect user intent using LLM. Returns whether Qdrant search is needed.
    Use this before sending chat to show appropriate loading indicator.
    
    Returns:
    - needs_qdrant_search: bool
    - intent_type: str (product_search, store_info, faq, chitchat, greeting, unknown)
    - confidence: float (0-1)
    """
    # If user is sending an image, always needs Qdrant search (image similarity)
    if has_image:
        return {
            "needs_qdrant_search": True,
            "intent_type": "product_search",
            "confidence": 1.0,
        }
    
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        _executor,
        lambda: detect_intent_with_llm(message),
    )
    return result


@router.post("/voice-detect-intent")
async def voice_detect_intent(
    voice: UploadFile = File(..., description="Audio file to transcribe and detect intent"),
    current_user: User = Depends(get_current_user),
):
    """
    Transcribe voice and detect intent using LLM.
    Use this before sending voice-chat to show appropriate loading indicator.
    
    Returns:
    - transcribed_text: str (the transcribed text from audio)
    - needs_qdrant_search: bool
    - intent_type: str (product_search, store_info, faq, chitchat, greeting, unknown)
    - confidence: float (0-1)
    """
    if not voice.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="voice file required")
    
    VOICE_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(voice.filename).suffix or ".webm"
    temp_path = VOICE_TEMP_DIR / f"{uuid.uuid4().hex}{suffix}"
    
    try:
        content = await voice.read()
        temp_path.write_bytes(content)
        
        # Transcribe audio
        loop = asyncio.get_event_loop()
        transcribed_text = await loop.run_in_executor(
            _executor,
            lambda: transcribe_audio(str(temp_path)),
        )
        
        if not transcribed_text or not transcribed_text.strip():
            return {
                "transcribed_text": "",
                "needs_qdrant_search": False,
                "intent_type": "unknown",
                "confidence": 0.5,
            }
        
        # Detect intent from transcribed text
        intent_result = await loop.run_in_executor(
            _executor,
            lambda: detect_intent_with_llm(transcribed_text),
        )
        
        return {
            "transcribed_text": transcribed_text,
            "needs_qdrant_search": intent_result.get("needs_qdrant_search", False),
            "intent_type": intent_result.get("intent_type", "unknown"),
            "confidence": intent_result.get("confidence", 0.5),
        }
    except Exception as e:
        # Fallback on error
        return {
            "transcribed_text": "",
            "needs_qdrant_search": True,  # Assume search needed on error
            "intent_type": "unknown",
            "confidence": 0.3,
        }
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


@router.get("/sessions", response_model=list[SessionResponse])
def list_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sessions = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.pinned.desc(), ChatSession.updated_at.desc())
        .all()
    )
    return sessions


@router.post("/sessions", response_model=SessionResponse)
def create_session(
    title: str = Form("New Chat"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = ChatSession(user_id=current_user.id, title=title)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@router.patch("/sessions/{session_id}", response_model=SessionResponse)
def update_session(
    session_id: int,
    body: SessionUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.user_id == current_user.id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if body.title is not None:
        session.title = body.title
    if body.pinned is not None:
        session.pinned = body.pinned
    db.commit()
    db.refresh(session)
    return session


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.user_id == current_user.id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    db.query(Message).filter(Message.session_id == session_id).delete()
    db.delete(session)
    db.commit()
    return None


@router.get("/sessions/{session_id}/messages", response_model=list[MessageOut])
def get_session_messages(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session = db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.user_id == current_user.id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session.messages


@router.get("/sessions/search", response_model=list[MessageSearchResult])
def search_sessions(
    q: str = Query(..., min_length=1, description="Search query in message content"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Search messages across all sessions of the current user. Returns matching messages with session info."""
    pattern = f"%{q.strip()}%"
    rows = (
        db.query(Message, ChatSession)
        .join(ChatSession, Message.session_id == ChatSession.id)
        .filter(ChatSession.user_id == current_user.id)
        .filter(Message.content.ilike(pattern))
        .order_by(Message.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        MessageSearchResult(
            message_id=m.id,
            session_id=m.session_id,
            session_title=s.title or "New Chat",
            role=m.role,
            content_snippet=(m.content[:200] + "…" if len(m.content) > 200 else m.content),
            created_at=m.created_at,
        )
        for m, s in rows
    ]


@router.post("/chat")
async def chat(
    session_id: int = Form(...),
    message: str = Form(""),
    image: UploadFile | None = File(None),
    top_k: int | None = Form(None, description="تعداد نتایج RAG (خالی = مقدار پیش‌فرض سرور)"),
    price_max: float | None = Form(None, description="حداکثر قیمت (فیلتر اختیاری)"),
    category: str | None = Form(None, description="دسته‌بندی (فیلتر اختیاری، تطبیق دقیق با category_name)"),
    selected_products: str | None = Form(None),
    sidebar_product: str | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Run RAG and return complete JSON response (no streaming)."""
    session = db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.user_id == current_user.id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    image_bytes = None
    if image and image.filename:
        image_bytes = await image.read()
    if not message.strip() and not image_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="message or image required")
    if top_k is not None and (top_k < 1 or top_k > 100):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="top_k must be between 1 and 100")

    user_text = message.strip() or "(user sent an image)"
    result = await _run_chat_response(
        db,
        session,
        current_user.id,
        user_text,
        image_bytes=image_bytes,
        top_k=top_k,
        price_max=price_max,
        category=category,
        attached_products=_parse_product_list(selected_products),
        sidebar_product=_parse_product_object(sidebar_product),
    )
    return _chat_payload(result)


@router.post("/voice-chat")
async def voice_chat(
    session_id: int = Form(...),
    voice: UploadFile = File(..., description="Audio file (e.g. webm, mp3, wav)"),
    selected_products: str | None = Form(None),
    sidebar_product: str | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Full voice conversation: STT -> RAG -> TTS. Returns JSON with message, products, and audio_base64.
    On TTS failure, returns message and products without audio (graceful degradation).
    
    If selected_products is provided (JSON array), the user's transcribed message will be prefixed
    with product context so the LLM knows which product(s) the user is asking about.
    """
    session = db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.user_id == current_user.id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if not voice.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="voice file required")

    VOICE_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(voice.filename).suffix or ".webm"
    temp_path = VOICE_TEMP_DIR / f"{uuid.uuid4().hex}{suffix}"
    try:
        content = await voice.read()
        temp_path.write_bytes(content)
    except Exception as e:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save voice file") from e

    try:
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(_executor, lambda: transcribe_audio(str(temp_path)))
    finally:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass

    if not (text and text.strip()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No speech detected. Please try again with a clearer recording.",
        )

    user_text = text.strip()
    result = await _run_chat_response(
        db,
        session,
        current_user.id,
        user_text,
        image_bytes=None,
        attached_products=_parse_product_list(selected_products),
        sidebar_product=_parse_product_object(sidebar_product),
    )
    payload = _chat_payload(result)
    payload["transcribed_text"] = user_text
    audio_base64 = None
    try:
        audio_bytes = await text_to_speech_to_bytes(result.message)
        if audio_bytes:
            audio_base64 = base64.b64encode(audio_bytes).decode("ascii")
    except Exception:
        pass
    if audio_base64 is not None:
        payload["audio_base64"] = audio_base64
    return payload


@router.post("/read-aloud")
async def read_aloud(
    text: str = Form(..., description="Text to synthesize (e.g. assistant message content)"),
    current_user: User = Depends(get_current_user),
):
    """
    Read aloud: detect language with LLM, then TTS with the appropriate voice.
    Returns audio_base64 (MP3) and detected_lang (ISO 639-1). For empty or very short text returns 400.
    """
    plain = _strip_markdown_for_tts(text)
    if not plain or len(plain) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Text is empty or too short to read aloud.",
        )
    loop = asyncio.get_event_loop()
    detected_lang = await loop.run_in_executor(
        _executor,
        lambda: detect_language_with_llm(plain),
    )
    audio_bytes = await text_to_speech_to_bytes(plain, lang=detected_lang)
    if not audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Text-to-speech failed. Please try again.",
        )
    audio_base64 = base64.b64encode(audio_bytes).decode("ascii")
    return {"audio_base64": audio_base64, "detected_lang": detected_lang}
