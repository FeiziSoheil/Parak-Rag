"""Ingestion API. Runs in background task. Allowed with Bearer token or X-API-Key."""
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, status, Header, Query, Depends

from app.config import INGEST_API_KEY, DATA_JSON_DIR, STORE_JSON_PATH, FAQ_JSON_PATH
from app.core.database import SessionLocal
from app.api.auth import get_optional_user, get_current_user
from app.models.user import User
from app.ingestion.qdrant_store import get_collection_points_count, store_store_records, store_faq_records

router = APIRouter()

# In-memory ingestion status (last run / current run) for step-by-step log display
_ingest_status: dict = {
    "status": "idle",
    "count": None,
    "limit": None,
    "finished_at": None,
    "total": None,
    "current_index": None,
    "current_subject": None,
}
_ingest_log: list[str] = []
_INGEST_LOG_MAX = 500
_ingest_lock = threading.Lock()
_ingest_cancel_requested = False
_INGEST_BATCH_SIZE = 15  # report progress after each batch


def _log(msg: str) -> None:
    """Append a timestamped line to _ingest_log (hold _ingest_lock)."""
    global _ingest_log
    line = f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}"
    _ingest_log.append(line)
    if len(_ingest_log) > _INGEST_LOG_MAX:
        _ingest_log = _ingest_log[-_INGEST_LOG_MAX:]


def run_ingestion(data_dir: str, limit: int | None = None):
    """Run ingestion in sync (called from thread/executor). If limit is set, only embed that many products.
    Updates _ingest_status after each batch for step-by-step log."""
    from app.ingestion.loader import load_all_products
    from app.ingestion.clip_embedder import get_embedder
    from app.ingestion.qdrant_store import store_products

    global _ingest_cancel_requested
    _ingest_cancel_requested = False
    # Set "running" immediately so the UI shows progress from the first poll (before slow load_all_products / get_embedder)
    with _ingest_lock:
        _ingest_log.clear()
        _ingest_status["status"] = "running"
        _ingest_status["count"] = None
        _ingest_status["limit"] = limit
        _ingest_status["finished_at"] = None
        _ingest_status["total"] = None
        _ingest_status["current_index"] = 0
        _ingest_status["current_subject"] = "Loading products…"
        _log(f"Starting ingestion (limit={limit if limit else 'all'})")
        _log("Loading products…")
    products = load_all_products(data_dir)
    if limit is not None and limit > 0:
        products = products[:limit]
    total = len(products)
    with _ingest_lock:
        _ingest_status["total"] = total
        _ingest_status["current_subject"] = "Loading model…"
        _log(f"Loaded {total} products. Loading CLIP model…")
    embedder = get_embedder()
    with _ingest_lock:
        _ingest_status["current_subject"] = None
        _log("Model ready. Embedding batches…")
    count = 0
    try:
        for start in range(0, total, _INGEST_BATCH_SIZE):
            with _ingest_lock:
                if _ingest_cancel_requested:
                    _log("Stop requested.")
                    break
            chunk = products[start : start + _INGEST_BATCH_SIZE]
            store_products(embedder, chunk)
            count = start + len(chunk)
            last_subject = (chunk[-1].get("subject") or "")[:60] if chunk else None
            with _ingest_lock:
                _ingest_status["current_index"] = count
                _ingest_status["current_subject"] = last_subject
                _log(f"Embedded products {start + 1}-{count} / {total}" + (f" — {last_subject}" if last_subject else ""))
        count = total
        with _ingest_lock:
            _log(f"Done. Embedded {count} products.")
    except Exception as e:
        count = 0
        with _ingest_lock:
            _log(f"Error: {e!s}")
        raise
    finally:
        with _ingest_lock:
            _ingest_status["status"] = "idle"
            _ingest_status["count"] = count
            _ingest_status["limit"] = limit
            _ingest_status["finished_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            _ingest_status["current_index"] = None
            _ingest_status["current_subject"] = None


@router.post("/ingest")
def trigger_ingest(
    background_tasks: BackgroundTasks,
    x_api_key: str | None = Header(None, alias="X-Api-Key"),
    data_dir: str | None = None,
    limit: int | None = Query(None, description="حداکثر تعداد محصول برای امبد؛ خالی = همه"),
    current_user: User | None = Depends(get_optional_user),
):
    allowed = current_user is not None or (INGEST_API_KEY and x_api_key == INGEST_API_KEY)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key or not authenticated")
    if limit is not None and limit < 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="limit must be >= 1")
    dir_to_use = data_dir or DATA_JSON_DIR
    background_tasks.add_task(run_ingestion, dir_to_use, limit)
    return {"status": "ingestion started", "data_dir": dir_to_use, "limit": limit}


@router.post("/ingest/stop")
def stop_ingest(
    current_user: User | None = Depends(get_optional_user),
    x_api_key: str | None = Header(None, alias="X-Api-Key"),
):
    """Request running ingestion to stop. Safe to call when no ingestion is running."""
    allowed = current_user is not None or (INGEST_API_KEY and x_api_key == INGEST_API_KEY)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key or not authenticated")
    global _ingest_cancel_requested
    with _ingest_lock:
        _ingest_cancel_requested = True
    return {"status": "stop requested"}


def run_store_faq_ingestion(store_json_path: Path | None = None, faq_json_path: Path | None = None):
    """Pipeline: load JSON -> upsert SQLite -> read from SQLite -> embed -> Qdrant (store + faq collections)."""
    store_path = store_json_path or STORE_JSON_PATH
    faq_path = faq_json_path or FAQ_JSON_PATH
    db = SessionLocal()
    try:
        from app.ingestion.store_faq_loader import (
            sync_store_json_to_db,
            sync_faq_json_to_db,
            get_store_records_for_embedding,
            get_faq_records_for_embedding,
        )
        from app.ingestion.clip_embedder import get_embedder

        if store_path.is_file():
            sync_store_json_to_db(store_path, db)
        if faq_path.is_file():
            sync_faq_json_to_db(faq_path, db)
        store_records = get_store_records_for_embedding(db)
        faq_records = get_faq_records_for_embedding(db)
        get_embedder()
        if store_records:
            store_store_records(store_records)
        if faq_records:
            store_faq_records(faq_records)
    finally:
        db.close()


@router.post("/ingest/store-faq")
def trigger_store_faq_ingest(
    background_tasks: BackgroundTasks,
    x_api_key: str | None = Header(None, alias="X-Api-Key"),
    current_user: User | None = Depends(get_optional_user),
):
    """Load store.json and faq.json, sync to SQLite, then embed and upsert to Qdrant (store + faq collections)."""
    allowed = current_user is not None or (INGEST_API_KEY and x_api_key == INGEST_API_KEY)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key or not authenticated")
    background_tasks.add_task(run_store_faq_ingestion, None, None)
    return {"status": "store-faq ingestion started", "store_json": str(STORE_JSON_PATH), "faq_json": str(FAQ_JSON_PATH)}


@router.get("/ingest/status")
def get_ingest_status(current_user: User = Depends(get_current_user)):
    """Return last/current ingestion run for step-by-step log display (auth required).
    When idle, also returns collection_count from Qdrant so the UI shows actual embedded points."""
    with _ingest_lock:
        payload = {
            "status": _ingest_status["status"],
            "count": _ingest_status["count"],
            "limit": _ingest_status["limit"],
            "finished_at": _ingest_status["finished_at"],
            "total": _ingest_status["total"],
            "current_index": _ingest_status["current_index"],
            "current_subject": _ingest_status["current_subject"],
            "log_lines": list(_ingest_log),
        }
    # When not running, add real collection count so frontend shows correct number (e.g. 15 products)
    if payload["status"] == "idle":
        try:
            collection_count = get_collection_points_count()
            payload["collection_count"] = collection_count
        except Exception:
            payload["collection_count"] = None
    else:
        payload["collection_count"] = None
    return payload