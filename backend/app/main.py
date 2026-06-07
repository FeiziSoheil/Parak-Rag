from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.database import engine, Base
from app.models import User, ChatSession, Message, StoreInfo, FAQ  # noqa: F401 - ensure all tables registered
from app.api import auth, chat, ingest, search as search_api, settings as settings_api


def _ensure_products_column():
    """Add messages.products column if missing (e.g. after deploy)."""
    if "sqlite" not in str(engine.url):
        return
    with engine.connect() as conn:
        r = conn.execute(text("PRAGMA table_info(messages)"))
        cols = [row[1] for row in r]
        if "products" not in cols:
            conn.execute(text("ALTER TABLE messages ADD COLUMN products TEXT"))
            conn.commit()


def _ensure_user_email_columns():
    """Add users.email and users.email_verified if missing (e.g. after deploy)."""
    if "sqlite" not in str(engine.url):
        return
    with engine.connect() as conn:
        r = conn.execute(text("PRAGMA table_info(users)"))
        cols = [row[1] for row in r]
        if "email" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(255)"))
            conn.commit()
        if "email_verified" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT 0"))
            conn.commit()
        for col, spec in [
            ("first_name", "VARCHAR(255)"),
            ("last_name", "VARCHAR(255)"),
            ("avatar_url", "VARCHAR(512)"),
        ]:
            if col not in cols:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {col} {spec}"))
                conn.commit()
        conn.execute(text("UPDATE users SET email_verified = 1 WHERE email_verified = 0 OR email_verified IS NULL"))
        conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    import logging
    import shutil
    from pathlib import Path

    from app.config import VOICE_TEMP_DIR
    from app.ingestion.clip_embedder import get_embedder

    logger = logging.getLogger(__name__)
    Base.metadata.create_all(bind=engine)
    _ensure_products_column()
    _ensure_user_email_columns()

    # Clear voice temp dir on startup (safety net for leftover files after crash/power loss)
    if VOICE_TEMP_DIR.exists():
        for p in VOICE_TEMP_DIR.iterdir():
            try:
                if p.is_file():
                    p.unlink()
                elif p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
            except OSError as e:
                logger.warning("Could not remove %s: %s", p, e)
    VOICE_TEMP_DIR.mkdir(parents=True, exist_ok=True)

    # Preload embedder at startup if possible; do not block startup on failure (e.g. network timeout to Hugging Face)
    offline_mode = os.environ.get("HF_HUB_OFFLINE", "0") == "1"
    try:
        loop = asyncio.get_event_loop()
        if offline_mode:
            logger.info("Offline mode enabled; attempting to load cached CLIP model...")
        else:
            logger.info("Online mode; attempting to preload CLIP model from HuggingFace...")
        await loop.run_in_executor(None, get_embedder)
        logger.info("✓ CLIP embedder preloaded successfully")
    except Exception as e:
        if offline_mode:
            logger.error(
                "CLIP preload failed in offline mode (cached model not available). Error: %s",
                e,
            )
        else:
            logger.warning(
                "CLIP preload failed (app will start; model will load on first use). Error: %s",
                e,
            )

    # Preload Whisper (STT) so first voice-chat request doesn't timeout while model downloads
    try:
        from app.services.stt import get_whisper_model
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, get_whisper_model)
        logger.info("✓ Whisper model preloaded successfully for voice chat")
    except Exception as e:
        logger.warning(
            "Whisper preload failed (app will start; model will load on first voice use). Error: %s",
            e,
        )

    yield
    # shutdown if needed


app = FastAPI(title="RAG Chatbot API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(chat.router, prefix="/api", tags=["chat", "sessions"])
app.include_router(ingest.router, prefix="/api", tags=["ingest"])
app.include_router(search_api.router, prefix="/api", tags=["search"])
app.include_router(settings_api.router, prefix="/api", tags=["settings"])
