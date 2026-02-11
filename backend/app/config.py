"""Application configuration. Use VECTOR_SIZE everywhere so changing CLIP model doesn't break Qdrant."""
import os
from pathlib import Path

from dotenv import load_dotenv

# بارگذاری .env از پوشه backend
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# CLIP vector size: openai/clip-vit-base-patch32 -> 512, laion/CLIP-ViT-L-14 -> 768
VECTOR_SIZE = int(os.getenv("VECTOR_SIZE", "512"))

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
BASE_DIR = Path(__file__).resolve().parent.parent

# JWT
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production-use-openssl-rand-hex-32")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# OpenRouter
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o")  # use gpt-oss-120b when available

# Qdrant
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "products")
QDRANT_COLLECTION_STORE = os.getenv("QDRANT_COLLECTION_STORE", "store")
QDRANT_COLLECTION_FAQ = os.getenv("QDRANT_COLLECTION_FAQ", "faq")

# RAG
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "5"))
RAG_SCORE_THRESHOLD = float(os.getenv("RAG_SCORE_THRESHOLD", "0.7"))
# Minimum similarity score to show products in chat (avoid showing irrelevant results when fallback threshold is used)
MIN_SCORE_TO_DISPLAY = float(os.getenv("MIN_SCORE_TO_DISPLAY", "0.35"))

# Ingestion — مسیر نسبی نسبت به backend حل می‌شود
_data_dir_raw = os.getenv("DATA_JSON_DIR", str(BASE_DIR.parent / "data" / "AE_Data"))
DATA_JSON_DIR = str((BASE_DIR / _data_dir_raw).resolve()) if not Path(_data_dir_raw).is_absolute() else _data_dir_raw
# Store and FAQ JSON (project root / data)
DATA_DIR = BASE_DIR.parent / "data"
STORE_JSON_PATH = DATA_DIR / "store.json"
FAQ_JSON_PATH = DATA_DIR / "faq.json"

# Ingest API protection (optional)
INGEST_API_KEY = os.getenv("INGEST_API_KEY", "")

# Email (SMTP) — for verification emails
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "noreply@yourdomain.com")
BASE_URL = os.getenv("BASE_URL", "http://localhost:3000")  # App URL for verification links

# Email verification token expiry (minutes)
VERIFICATION_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

# Verification code (numeric code sent in email)
VERIFICATION_CODE_LENGTH = 6
VERIFICATION_CODE_EXPIRE_MINUTES = 2  # 2 minutes
VERIFICATION_CODE_MAX_REQUESTS = 3  # max times user can request code (register + resends)
VERIFICATION_CODE_LOCK_MINUTES = 60 * 2  # 2 hours lock after max requests

# Avatar uploads (relative to backend)
AVATAR_UPLOAD_DIR = BASE_DIR / "uploads" / "avatars"

# Voice (STT/TTS)
VOICE_TEMP_DIR = BASE_DIR / "temp" / "voice"
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "small")
TTS_VOICE_FA = os.getenv("TTS_VOICE_FA", "fa-IR-DilaraNeural")
TTS_VOICE_EN = os.getenv("TTS_VOICE_EN", "en-US-JennyNeural")
TTS_VOICE_TR = os.getenv("TTS_VOICE_TR", "tr-TR-EmelNeural")
TTS_VOICE = os.getenv("TTS_VOICE", "fa-IR-DilaraNeural")
