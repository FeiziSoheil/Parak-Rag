"""Settings API: read-only RAG/config values for UI."""
from fastapi import APIRouter, Depends

from app.api.auth import get_current_user
from app.config import RAG_TOP_K, RAG_SCORE_THRESHOLD, MIN_SCORE_TO_DISPLAY
from app.models.user import User

router = APIRouter()


@router.get("/settings")
def get_settings(
    current_user: User = Depends(get_current_user),
):
    """Return RAG and related settings for the UI (read-only from env)."""
    return {
        "rag_top_k": RAG_TOP_K,
        "rag_score_threshold": RAG_SCORE_THRESHOLD,
        "min_score_to_display": MIN_SCORE_TO_DISPLAY,
    }
