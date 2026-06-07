"""Load store and FAQ from JSON, sync to SQLite, and build context_text with prefix for embedding.
Single source of truth: ingest flow is JSON -> SQLite -> read from SQLite -> embed -> Qdrant."""
import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.store_info import StoreInfo
from app.models.faq import FAQ


def _safe_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def load_store_from_json(path: str | Path) -> list[dict]:
    """Load store records from a JSON file. Returns list of dicts with id, name, description, address, working_hours, phone, email."""
    p = Path(path)
    if not p.is_file():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(raw, list):
        raw = [raw] if isinstance(raw, dict) else []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        sid = item.get("id")
        if sid is None:
            continue
        out.append({
            "id": int(sid) if isinstance(sid, (int, float)) else sid,
            "name": _safe_str(item.get("name")),
            "description": _safe_str(item.get("description")),
            "address": _safe_str(item.get("address")),
            "working_hours": _safe_str(item.get("working_hours")),
            "phone": _safe_str(item.get("phone")),
            "email": _safe_str(item.get("email")),
        })
    return out


def load_faq_from_json(path: str | Path) -> list[dict]:
    """Load FAQ records from a JSON file. Returns list of dicts with id, question, answer, category."""
    p = Path(path)
    if not p.is_file():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(raw, list):
        raw = [raw] if isinstance(raw, dict) else []
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        fid = item.get("id")
        if fid is None:
            continue
        out.append({
            "id": int(fid) if isinstance(fid, (int, float)) else fid,
            "question": _safe_str(item.get("question")),
            "answer": _safe_str(item.get("answer")),
            "category": _safe_str(item.get("category")) or None,
        })
    return out


def build_store_context_text(record: dict) -> str:
    """Build context_text with bilingual labels so queries in any language match (embedding + LLM)."""
    parts = []
    if record.get("name"):
        parts.append(f"Store name / نام فروشگاه: {record['name']}")
    if record.get("description"):
        parts.append(f"Description / توضیحات: {record['description']}")
    if record.get("address"):
        parts.append(f"Address / آدرس: {record['address']}")
    if record.get("working_hours"):
        parts.append(f"Working hours / ساعات کاری: {record['working_hours']}")
    if record.get("phone"):
        parts.append(f"Phone / تلفن: {record['phone']}")
    if record.get("email"):
        parts.append(f"Email / ایمیل: {record['email']}")
    return "\n".join(parts) if parts else ""


def build_faq_context_text(record: dict) -> str:
    """Build context_text with bilingual labels so queries in any language match (embedding + LLM)."""
    parts = []
    if record.get("question"):
        parts.append(f"Question / سوال: {record['question']}")
    if record.get("answer"):
        parts.append(f"Answer / پاسخ: {record['answer']}")
    if record.get("category"):
        parts.append(f"Category / دسته: {record['category']}")
    return "\n".join(parts) if parts else ""


def sync_store_json_to_db(json_path: str | Path, db: Session) -> int:
    """Load store.json, upsert into store_info table. Returns number of records upserted."""
    records = load_store_from_json(json_path)
    count = 0
    for r in records:
        sid = r["id"]
        existing = db.query(StoreInfo).filter(StoreInfo.id == sid).first()
        if existing:
            existing.name = r["name"]
            existing.description = r["description"] or None
            existing.address = r["address"] or None
            existing.working_hours = r["working_hours"] or None
            existing.phone = r["phone"] or None
            existing.email = r["email"] or None
        else:
            db.add(StoreInfo(
                id=sid,
                name=r["name"],
                description=r["description"] or None,
                address=r["address"] or None,
                working_hours=r["working_hours"] or None,
                phone=r["phone"] or None,
                email=r["email"] or None,
            ))
        count += 1
    db.commit()
    return count


def sync_faq_json_to_db(json_path: str | Path, db: Session) -> int:
    """Load faq.json, upsert into faq table. Returns number of records upserted."""
    records = load_faq_from_json(json_path)
    count = 0
    for r in records:
        fid = r["id"]
        existing = db.query(FAQ).filter(FAQ.id == fid).first()
        if existing:
            existing.question = r["question"]
            existing.answer = r["answer"]
            existing.category = r["category"] or None
        else:
            db.add(FAQ(
                id=fid,
                question=r["question"],
                answer=r["answer"],
                category=r["category"] or None,
            ))
        count += 1
    db.commit()
    return count


def get_store_records_for_embedding(db: Session) -> list[dict]:
    """Read all store_info from DB and return list of dicts with context_text and payload fields for Qdrant."""
    rows = db.query(StoreInfo).order_by(StoreInfo.id).all()
    out = []
    for row in rows:
        record = {
            "id": row.id,
            "name": row.name or "",
            "description": row.description or "",
            "address": row.address or "",
            "working_hours": row.working_hours or "",
            "phone": row.phone or "",
            "email": row.email or "",
        }
        context_text = build_store_context_text(record)
        record["context_text"] = context_text
        out.append(record)
    return out


def get_faq_records_for_embedding(db: Session) -> list[dict]:
    """Read all FAQ from DB and return list of dicts with context_text and payload fields for Qdrant."""
    rows = db.query(FAQ).order_by(FAQ.id).all()
    out = []
    for row in rows:
        record = {
            "id": row.id,
            "question": row.question or "",
            "answer": row.answer or "",
            "category": row.category,
        }
        context_text = build_faq_context_text(
            {"question": record["question"], "answer": record["answer"], "category": record["category"]}
        )
        record["context_text"] = context_text
        out.append(record)
    return out
