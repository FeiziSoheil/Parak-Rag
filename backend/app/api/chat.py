"""Chat and sessions API. Chat endpoint accepts multipart/form-data and returns JSON response."""
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.database import get_db, SessionLocal
from app.models.user import User
from app.models.session import ChatSession
from app.models.message import Message
from app.schemas.chat import SessionResponse, MessageOut
from app.services.memory import get_chat_history
from app.services.rag import (
    run_embed_and_search,
    enhanced_search_with_llm,
    filter_search_results_by_min_score,
    build_context,
    build_combined_context,
    run_rag_response,
    is_product_related_query,
    is_broad_products_query,
    products_from_search_results,
    get_query_vector,
    search_store,
    search_faq,
)

router = APIRouter()
_executor = ThreadPoolExecutor(max_workers=4)


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

    loop = asyncio.get_event_loop()
    user_text = message.strip() or None
    effective_message = message.strip() or "(user sent an image)"

    # Determine if we need product search
    do_product_search = is_product_related_query(user_text) or image_bytes is not None
    if do_product_search:
        if image_bytes:
            # Image search: embed image and search (no LLM keyword extraction)
            search_results = await loop.run_in_executor(
                _executor,
                lambda: run_embed_and_search(
                    user_text, image_bytes, top_k=top_k, price_max=price_max, category=category
                ),
            )
        else:
            # Text query: use enhanced search (LLM extracts keywords/category, incl. Persian→English) for better accuracy
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
        # Only show products that meet minimum relevance (avoid showing irrelevant results from low-threshold fallback). Skip filter for "show all" queries.
        if not is_broad_products_query(user_text):
            search_results = filter_search_results_by_min_score(search_results)
        products = products_from_search_results(search_results)
        # Parallel search in store and FAQ (same query vector), then build combined context
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

    # Get chat history and generate response (non-streaming)
    history = get_chat_history(db, session_id)
    search_by_image = image_bytes is not None
    full_text = await loop.run_in_executor(
        _executor,
        lambda: run_rag_response(context, history, effective_message, search_by_image=search_by_image),
    )

    # Save user and assistant messages
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

    return {"message": full_text, "products": products}
