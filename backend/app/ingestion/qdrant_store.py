"""Store product vectors in Qdrant. Idempotent: use deterministic UUIDs from product_id (and img idx) as point id."""
import logging
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from app.config import QDRANT_URL, QDRANT_COLLECTION, QDRANT_COLLECTION_STORE, QDRANT_COLLECTION_FAQ
from app.ingestion.clip_embedder import get_embedder, embed_texts, embed_image_url, get_embedding_dim

# برای id یکتا و قطعی (re-ingest همان نقطه را overwrite می‌کند)
_log = logging.getLogger(__name__)
_POINT_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "qdrant.products.local")
_POINT_NAMESPACE_STORE = uuid.uuid5(uuid.NAMESPACE_DNS, "qdrant.store.local")
_POINT_NAMESPACE_FAQ = uuid.uuid5(uuid.NAMESPACE_DNS, "qdrant.faq.local")


def _collection_vector_size(client: QdrantClient, collection: str) -> int | None:
    """Return the vector size of the collection's default vector, or None if not found."""
    try:
        info = client.get_collection(collection)
        vectors = info.config.params.vectors
        if vectors is None:
            return None
        # Single-vector: VectorParams with .size; named: dict of name -> VectorParams
        if hasattr(vectors, "size"):
            return vectors.size
        if isinstance(vectors, dict) and vectors:
            first = next(iter(vectors.values()))
            return getattr(first, "size", None)
        return None
    except Exception:
        return None


def get_collection_points_count(collection: str = QDRANT_COLLECTION) -> int | None:
    """Return the number of points in the collection, or None on error."""
    try:
        client = QdrantClient(url=QDRANT_URL)
        result = client.count(collection_name=collection, exact=False)
        return result.count
    except Exception:
        return None


def ensure_collection(client: QdrantClient, collection: str = QDRANT_COLLECTION):
    """Create collection if not exists with size = get_embedding_dim() (matches loaded embedder).
    If collection exists but vector size differs (e.g. embedder changed), delete and recreate it.
    """
    expected_size = get_embedding_dim()
    collections = client.get_collections().collections
    exists = any(c.name == collection for c in collections)
    if exists:
        current_size = _collection_vector_size(client, collection)
        if current_size is not None and current_size != expected_size:
            client.delete_collection(collection)
            exists = False
    if not exists:
        client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=expected_size, distance=Distance.COSINE),
        )
    return collection


def _point_id_text(product_id) -> uuid.UUID:
    """Deterministic UUID for text point (idempotent upsert)."""
    return uuid.uuid5(_POINT_NAMESPACE, f"{product_id}_text")


def _point_id_image(product_id, img_idx: int) -> uuid.UUID:
    """Deterministic UUID for image point (idempotent upsert)."""
    return uuid.uuid5(_POINT_NAMESPACE, f"{product_id}_img_{img_idx}")


def store_products(embedder, products: list[dict], collection: str = QDRANT_COLLECTION):
    """Embed and upsert products. Point id = UUID from product_id (and img idx) for Qdrant compatibility (idempotent overwrite)."""
    client = QdrantClient(url=QDRANT_URL)
    ensure_collection(client, collection)
    texts = [p["context_text"] for p in products]
    text_vectors = embed_texts(texts)
    points = []
    for i, (prod, vec) in enumerate(zip(products, text_vectors)):
        pid = prod["product_id"]
        image_urls = prod.get("image_urls") or []
        payload = {
            "product_id": pid,
            "context_text": prod["context_text"],
            "subject": prod["subject"],
            "price": prod.get("price"),
            "category_id": prod.get("category_id"),
            "category_name": prod.get("category_name", ""),
            "type": "text",
            "image_urls": image_urls,
            "main_image_url": prod.get("main_image_url") or (image_urls[0] if image_urls else ""),
            "variants": prod.get("variants") or [],
        }
        points.append(PointStruct(id=_point_id_text(pid), vector=vec, payload=payload))
    if points:
        client.upsert(collection_name=collection, points=points)
    for prod in products:
        image_urls = prod.get("image_urls") or []
        for idx, url in enumerate(image_urls[:3]):
            try:
                vec = embed_image_url(url)
            except Exception as e:
                _log.warning("Image embed skipped for product_id=%s url=%s: %s", prod.get("product_id"), url[:80] if url else "", e)
                continue
            pid = prod["product_id"]
            payload = {
                "product_id": pid,
                "context_text": prod["context_text"],
                "subject": prod["subject"],
                "price": prod.get("price"),
                "category_id": prod.get("category_id"),
                "category_name": prod.get("category_name", ""),
                "type": "image",
                "image_url": url,
                "main_image_url": prod.get("main_image_url") or (image_urls[0] if image_urls else ""),
                "variants": prod.get("variants") or [],
            }
            points_img = [PointStruct(id=_point_id_image(pid, idx), vector=vec, payload=payload)]
            client.upsert(collection_name=collection, points=points_img)


def _point_id_store(store_id: int) -> uuid.UUID:
    """Deterministic UUID for store point (idempotent upsert)."""
    return uuid.uuid5(_POINT_NAMESPACE_STORE, f"store_{store_id}")


def _point_id_faq(faq_id: int) -> uuid.UUID:
    """Deterministic UUID for FAQ point (idempotent upsert)."""
    return uuid.uuid5(_POINT_NAMESPACE_FAQ, f"faq_{faq_id}")


def store_store_records(
    records: list[dict],
    collection_name: str = QDRANT_COLLECTION_STORE,
) -> None:
    """Embed store records (from DB) and upsert into Qdrant. Each record must have context_text, id, name, address, working_hours, phone, email."""
    if not records:
        return
    texts = [r["context_text"] for r in records]
    text_vectors = embed_texts(texts)
    client = QdrantClient(url=QDRANT_URL)
    ensure_collection(client, collection_name)
    points = []
    for r, vec in zip(records, text_vectors):
        sid = r["id"]
        points.append(PointStruct(
            id=_point_id_store(sid),
            vector=vec,
            payload={
                "store_id": sid,
                "context_text": r["context_text"],
                "name": r.get("name", ""),
                "address": r.get("address", ""),
                "working_hours": r.get("working_hours", ""),
                "phone": r.get("phone", ""),
                "email": r.get("email", ""),
            },
        ))
    client.upsert(collection_name=collection_name, points=points)


def store_faq_records(
    records: list[dict],
    collection_name: str = QDRANT_COLLECTION_FAQ,
) -> None:
    """Embed FAQ records (from DB) and upsert into Qdrant. Each record must have context_text, id, question, answer, category."""
    if not records:
        return
    texts = [r["context_text"] for r in records]
    text_vectors = embed_texts(texts)
    client = QdrantClient(url=QDRANT_URL)
    ensure_collection(client, collection_name)
    points = []
    for r, vec in zip(records, text_vectors):
        fid = r["id"]
        points.append(PointStruct(
            id=_point_id_faq(fid),
            vector=vec,
            payload={
                "faq_id": fid,
                "context_text": r["context_text"],
                "question": r.get("question", ""),
                "answer": r.get("answer", ""),
                "category": r.get("category"),
            },
        ))
    client.upsert(collection_name=collection_name, points=points)
