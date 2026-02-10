#!/usr/bin/env python3
"""استخراج تمام محصولات از Qdrant و تولید گزارش کامل.
از نقاط با type=text یک رکورد یکتا به ازای هر product_id می‌سازد.
"""
import json
import os
import sys
from pathlib import Path

# backend/scripts -> backend
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.chdir(Path(__file__).resolve().parent.parent)

from qdrant_client import QdrantClient

from app.config import QDRANT_URL, QDRANT_COLLECTION
from app.ingestion.qdrant_store import ensure_collection


def extract_products_from_qdrant(collection: str = QDRANT_COLLECTION) -> list[dict]:
    """Scroll کل collection و لیست یکتای محصولات (یک نقطه text به ازای هر product_id)."""
    client = QdrantClient(url=QDRANT_URL)
    ensure_collection(client, collection)
    seen_ids = set()
    products = []
    offset = None
    batch_size = 500
    while True:
        scroll_result = client.scroll(
            collection_name=collection,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        points, next_offset = scroll_result
        if not points:
            break
        for point in points:
            payload = point.payload or {}
            pid = payload.get("product_id")
            if pid is None or pid in seen_ids:
                continue
            # فقط نقاط متن را به‌عنوان نماینده محصول نگه می‌داریم (context_text کامل)
            point_type = payload.get("type") or "text"
            if point_type != "text":
                continue
            seen_ids.add(pid)
            products.append({
                "product_id": pid,
                "subject": payload.get("subject") or "",
                "price": payload.get("price"),
                "category_id": payload.get("category_id"),
                "category_name": payload.get("category_name") or "",
                "context_text": payload.get("context_text") or "",
                "image_urls": payload.get("image_urls") or [],
                "variants": payload.get("variants") or [],
            })
        offset = next_offset
        if offset is None:
            break
    # اگر فقط نقطه image داشتیم و text نداشتیم، از همان image استفاده کن
    if not products:
        offset = None
        while True:
            scroll_result = client.scroll(
                collection_name=collection,
                limit=batch_size,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            points, next_offset = scroll_result
            if not points:
                break
            for point in points:
                payload = point.payload or {}
                pid = payload.get("product_id")
                if pid is None or pid in seen_ids:
                    continue
                seen_ids.add(pid)
                products.append({
                    "product_id": pid,
                    "subject": payload.get("subject") or "",
                    "price": payload.get("price"),
                    "category_id": payload.get("category_id"),
                    "category_name": payload.get("category_name") or "",
                    "context_text": payload.get("context_text") or "",
                    "image_urls": payload.get("image_urls") or [],
                    "image_url": payload.get("image_url"),
                    "variants": payload.get("variants") or [],
                })
            offset = next_offset
            if offset is None:
                break
    return sorted(products, key=lambda p: (p.get("category_name") or "", p.get("product_id") or 0))


def build_summary(products: list[dict]) -> dict:
    """آمار کلی: تعداد، دسته‌ها، قیمت."""
    categories = {}
    prices = []
    for p in products:
        cat = (p.get("category_name") or "").strip() or "بدون دسته"
        categories[cat] = categories.get(cat, 0) + 1
        pr = p.get("price")
        if pr is not None:
            try:
                prices.append(float(pr))
            except (TypeError, ValueError):
                pass
    stats = {
        "total_products": len(products),
        "categories": dict(sorted(categories.items(), key=lambda x: -x[1])),
        "category_count": len(categories),
    }
    if prices:
        stats["price"] = {
            "min": min(prices),
            "max": max(prices),
            "avg": round(sum(prices) / len(prices), 2),
            "count": len(prices),
        }
    return stats


def write_report(products: list[dict], out_dir: Path) -> None:
    """خروجی: products.json و report.md."""
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = build_summary(products)
    # JSON کامل
    json_path = out_dir / "products_from_qdrant.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "products": products}, f, ensure_ascii=False, indent=2)
    # گزارش متنی
    md_path = out_dir / "product_report.md"
    lines = [
        "# گزارش محصولات استخراج‌شده از Qdrant",
        "",
        f"**تعداد کل محصولات:** {summary['total_products']}",
        f"**تعداد دسته‌ها:** {summary['category_count']}",
        "",
    ]
    if summary.get("price"):
        p = summary["price"]
        lines.extend([
            "## آمار قیمت",
            f"- کمینه: {p['min']}",
            f"- بیشینه: {p['max']}",
            f"- میانگین: {p['avg']}",
            f"- تعداد با قیمت: {p['count']}",
            "",
        ])
    lines.extend(["## توزیع بر اساس دسته", ""])
    for cat, count in summary.get("categories", {}).items():
        lines.append(f"- **{cat}**: {count}")
    lines.extend(["", "---", "", "## لیست محصولات", ""])
    for p in products:
        sid = p.get("product_id", "")
        subj = (p.get("subject") or "")[:80]
        price = p.get("price")
        cat = p.get("category_name") or ""
        price_str = f" — {price}" if price is not None else ""
        lines.append(f"- **{sid}** — {subj}{price_str} — {cat}")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"خروجی JSON: {json_path}")
    print(f"گزارش متنی: {md_path}")


def main():
    collection = os.getenv("QDRANT_COLLECTION", QDRANT_COLLECTION)
    out_dir = Path(__file__).resolve().parent.parent / "reports"
    print(f"اتصال به Qdrant و collection: {collection} ...")
    products = extract_products_from_qdrant(collection)
    print(f"تعداد محصولات یکتا: {len(products)}")
    if not products:
        print("هیچ محصولی در Qdrant یافت نشد.")
        return
    write_report(products, out_dir)
    print("پایان.")


if __name__ == "__main__":
    main()
