"""Chat history: rolling window (last N messages) for same session_id."""
from sqlalchemy.orm import Session
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

from app.models.message import Message

HISTORY_LIMIT = 10


def get_chat_history(db: Session, session_id: int, limit: int = HISTORY_LIMIT) -> list[BaseMessage]:
    """Load last N messages for session and return as LangChain messages."""
    rows = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
        .all()
    )
    rows = list(reversed(rows))
    out: list[BaseMessage] = []
    for m in rows:
        if m.role == "user":
            out.append(HumanMessage(content=m.content))
        elif m.role == "assistant":
            out.append(AIMessage(content=m.content))
    return out
