"""Chat and sessions API. Chat endpoint accepts multipart/form-data and returns JSON response."""
import asyncio
import base64
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.config import VOICE_TEMP_DIR
from app.core.database import get_db, SessionLocal
from app.models.user import User
from app.models.session import ChatSession
from app.models.message import Message
from app.schemas.chat import SessionResponse, MessageOut, MessageSearchResult
from app.services.memory import get_chat_history
from app.services.rag import (
    run_embed_and_search,
    enhanced_search_with_llm,
    filter_search_results_by_min_score,
    build_combined_context,
    run_rag_response,
    is_broad_products_query,
    products_from_search_results,
    get_query_vector,
    search_store,
    search_faq,
    detect_intent_with_llm,
)
from app.services.stt import transcribe_audio
from app.services.tts import text_to_speech_to_bytes

router = APIRouter()
_executor = ThreadPoolExecutor(max_workers=4)


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


async def _run_chat_response(
    db: Session,
    session_id: int,
    effective_message: str,
    image_bytes: bytes | None = None,
    top_k: int | None = None,
    price_max: float | None = None,
    category: str | None = None,
) -> tuple[str, list]:
    """
    Run RAG pipeline and save user/assistant messages. Returns (full_text, products).
    Shared by POST /chat and POST /voice-chat.
    """
    loop = asyncio.get_event_loop()
    user_text = None if effective_message == "(user sent an image)" else (effective_message or None)

    # Use LLM-based intent detection instead of keyword matching
    if image_bytes:
        do_product_search = True
    else:
        intent_result = await loop.run_in_executor(
            _executor,
            lambda: detect_intent_with_llm(user_text),
        )
        do_product_search = intent_result.get("needs_qdrant_search", False)
    
    if do_product_search:
        if image_bytes:
            search_results = await loop.run_in_executor(
                _executor,
                lambda: run_embed_and_search(
                    user_text, image_bytes, top_k=top_k, price_max=price_max, category=category
                ),
            )
        else:
            last_shown = _get_last_shown_products(db, session_id)
            enhanced = await loop.run_in_executor(
                _executor,
                lambda: enhanced_search_with_llm(
                    user_query=user_text or "",
                    limit=top_k or 10,
                    price_max=price_max,
                    category=category,
                    last_shown_products=last_shown,
                ),
            )
            search_results = enhanced["results"]
        if not is_broad_products_query(user_text):
            search_results = filter_search_results_by_min_score(search_results)
        products = products_from_search_results(search_results)
        query_vector = await loop.run_in_executor(
            _executor,
            lambda: get_query_vector(user_text, image_bytes),
        )
        store_results = await loop.run_in_executor(
            _executor,
            lambda: search_store(query_vector, top_k=3),
        )
        faq_results = await loop.run_in_executor(
            _executor,
            lambda: search_faq(query_vector, top_k=5),
        )
        context = build_combined_context(store_results, faq_results, search_results)
    else:
        context = "No relevant products found."
        products = []

    history = get_chat_history(db, session_id)
    search_by_image = image_bytes is not None
    full_text = await loop.run_in_executor(
        _executor,
        lambda: run_rag_response(context, history, effective_message, search_by_image=search_by_image),
    )

    db2 = SessionLocal()
    try:
        user_msg = Message(session_id=session_id, role="user", content=effective_message, image_url=None)
        db2.add(user_msg)
        assistant_msg = Message(
            session_id=session_id,
            role="assistant",
            content=full_text,
            products=json.dumps(products) if products else None,
        )
        db2.add(assistant_msg)
        sess = db2.query(ChatSession).filter(ChatSession.id == session_id).first()
        if sess and sess.title == "New Chat" and effective_message:
            sess.title = effective_message[:100] + ("..." if len(effective_message) > 100 else "")
        db2.commit()
    finally:
        db2.close()

    return full_text, products


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
    sessions = db.query(ChatSession).filter(ChatSession.user_id == current_user.id).order_by(ChatSession.updated_at.desc()).all()
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

    effective_message = message.strip() or "(user sent an image)"
    full_text, products = await _run_chat_response(
        db, session_id, effective_message,
        image_bytes=image_bytes, top_k=top_k, price_max=price_max, category=category,
    )
    return {"message": full_text, "products": products}


@router.post("/voice-chat")
async def voice_chat(
    session_id: int = Form(...),
    voice: UploadFile = File(..., description="Audio file (e.g. webm, mp3, wav)"),
    selected_products: str | None = Form(None, description="JSON array of selected products (product_id, subject, price, category_name)"),
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

    # Parse selected products if provided
    attached_products: list[dict] = []
    if selected_products and selected_products.strip():
        try:
            attached_products = json.loads(selected_products)
            if not isinstance(attached_products, list):
                attached_products = []
        except (json.JSONDecodeError, TypeError):
            attached_products = []

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

    # Build effective message with product context if products are selected
    transcribed_text = text.strip()
    if attached_products:
        product_context = _format_product_context(attached_products)
        effective_message = product_context + transcribed_text
    else:
        effective_message = transcribed_text

    full_text, products = await _run_chat_response(
        db, session_id, effective_message, image_bytes=None,
    )

    audio_base64 = None
    try:
        audio_bytes = await text_to_speech_to_bytes(full_text)
        if audio_bytes:
            audio_base64 = base64.b64encode(audio_bytes).decode("ascii")
    except Exception:
        pass

    response = {
        "message": full_text,
        "products": products,
        "transcribed_text": text.strip(),
    }
    if audio_base64 is not None:
        response["audio_base64"] = audio_base64
    return response
