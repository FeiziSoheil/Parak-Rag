#!/usr/bin/env python3
"""گزارش جامع آماری از دیتابیس Qdrant: تمام کالکشن‌ها، تعداد نقاط، وکتور، آمار محصولات/فروشگاه/سوالات متداول."""
import os
import sys
from pathlib import Path
from datetime import datetime

# backend/scripts -> backend
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.chdir(Path(__file__).resolve().parent.parent)

from qdrant_client import QdrantClient

from app.config import (
    QDRANT_URL,
    QDRANT_COLLECTION,
    QDRANT_COLLECTION_STORE,
    QDRANT_COLLECTION_FAQ,
)


def _collection_vector_size(client: QdrantClient, collection: str) -> int | None:
    """بعد وکتور کالکشن (بدون وابستگی به clip_embedder)."""
    try:
        info = client.get_collection(collection)
        vectors = info.config.params.vectors
        if vectors is None:
            return None
        if hasattr(vectors, "size"):
            return vectors.size
        if isinstance(vectors, dict) and vectors:
            first = next(iter(vectors.values()))
            return getattr(first, "size", None)
        return None
    except Exception:
        return None


def get_all_collection_names(client: QdrantClient) -> list[str]:
    """لیست نام تمام کالکشن‌های موجود در Qdrant."""
    try:
        return [c.name for c in client.get_collections().collections]
    except Exception:
        return []


def get_collection_info(client: QdrantClient, name: str) -> dict | None:
    """اطلاعات یک کالکشن: تعداد نقاط، بعد وکتور. در صورت خطا None."""
    try:
        count = client.count(collection_name=name, exact=True)
        vector_size = _collection_vector_size(client, name)
        return {"points_count": count.count, "vector_size": vector_size}
    except Exception:
        return None


def stats_products(client: QdrantClient, collection: str) -> dict:
    """آمار تفصیلی کالکشن محصولات: نقاط متنی/تصویری، محصولات یکتا، دسته‌ها، قیمت."""
    out = {
        "total_points": 0,
        "points_text": 0,
        "points_image": 0,
        "unique_products": set(),
        "categories": {},
        "prices": [],
    }
    offset = None
    batch = 1000
    while True:
        try:
            points, next_offset = client.scroll(
                collection_name=collection,
                limit=batch,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
        except Exception:
            break
        if not points:
            break
        for point in points:
            out["total_points"] += 1
            p = point.payload or {}
            t = (p.get("type") or "text").lower()
            if t == "image":
                out["points_image"] += 1
            else:
                out["points_text"] += 1
            pid = p.get("product_id")
            if pid is not None:
                out["unique_products"].add(pid)
            cat = (p.get("category_name") or "").strip() or "بدون دسته"
            out["categories"][cat] = out["categories"].get(cat, 0) + 1
            price = p.get("price")
            if price is not None:
                try:
                    out["prices"].append(float(price))
                except (TypeError, ValueError):
                    pass
        offset = next_offset
        if offset is None:
            break
    # تبدیل set به عدد و محاسبه آمار قیمت
    out["unique_products"] = len(out["unique_products"])
    if out["prices"]:
        out["price_min"] = min(out["prices"])
        out["price_max"] = max(out["prices"])
        out["price_avg"] = sum(out["prices"]) / len(out["prices"])
        out["price_count"] = len(out["prices"])
    else:
        out["price_min"] = out["price_max"] = out["price_avg"] = out["price_count"] = None
    del out["prices"]
    return out


def stats_store(client: QdrantClient, collection: str) -> dict:
    """آمار کالکشن فروشگاه: تعداد، نام‌ها، آدرس‌ها."""
    names = []
    offset = None
    batch = 500
    while True:
        try:
            points, next_offset = client.scroll(
                collection_name=collection,
                limit=batch,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
        except Exception:
            break
        if not points:
            break
        for point in points:
            p = point.payload or {}
            names.append(p.get("name") or p.get("address") or "(بدون نام)")
        offset = next_offset
        if offset is None:
            break
    return {"count": len(names), "names": names}


def stats_faq(client: QdrantClient, collection: str) -> dict:
    """آمار کالکشن FAQ: تعداد، دسته‌ها، نمونه سوالات."""
    categories = {}
    questions = []
    total = 0
    offset = None
    batch = 500
    while True:
        try:
            points, next_offset = client.scroll(
                collection_name=collection,
                limit=batch,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
        except Exception:
            break
        if not points:
            break
        for point in points:
            total += 1
            p = point.payload or {}
            cat = (p.get("category") or "").strip() or "بدون دسته"
            categories[cat] = categories.get(cat, 0) + 1
            q = (p.get("question") or "").strip()
            if q and len(questions) < 20:
                questions.append(q[:100])
        offset = next_offset
        if offset is None:
            break
    return {"count": total, "categories": categories, "sample_questions": questions}


def build_report() -> str:
    """ساخت متن گزارش به صورت Markdown."""
    client = QdrantClient(url=QDRANT_URL)
    lines = [
        "# گزارش جامع آماری دیتابیس Qdrant",
        "",
        f"**تاریخ تولید:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**آدرس Qdrant:** `{QDRANT_URL}`",
        "",
        "---",
        "",
    ]

    all_collections = get_all_collection_names(client)
    lines.append("## خلاصه کالکشن‌ها")
    lines.append("")
    lines.append("| کالکشن | تعداد نقاط | بعد وکتور |")
    lines.append("|--------|------------|-----------|")

    for col_name in [QDRANT_COLLECTION, QDRANT_COLLECTION_STORE, QDRANT_COLLECTION_FAQ]:
        if col_name not in all_collections:
            lines.append(f"| {col_name} | — (وجود ندارد) | — |")
            continue
        info = get_collection_info(client, col_name)
        if info:
            pts = info.get("points_count", "—")
            dim = info.get("vector_size") or "—"
            lines.append(f"| {col_name} | {pts} | {dim} |")
        else:
            lines.append(f"| {col_name} | خطا | — |")

    # ——— محصولات ———
    lines.extend(["", "---", "", "## کالکشن محصولات (Products)", ""])
    if QDRANT_COLLECTION in all_collections:
        info = get_collection_info(client, QDRANT_COLLECTION)
        if info:
            lines.append(f"- **تعداد کل نقاط (بردار):** {info['points_count']}")
            lines.append(f"- **بعد وکتور:** {info.get('vector_size') or '—'}")
        try:
            prod_stats = stats_products(client, QDRANT_COLLECTION)
            lines.extend([
                f"- **نقاط متنی (text):** {prod_stats['points_text']}",
                f"- **نقاط تصویری (image):** {prod_stats['points_image']}",
                f"- **تعداد محصولات یکتا:** {prod_stats['unique_products']}",
                "",
            ])
            if prod_stats["points_image"] == 0:
                lines.extend([
                    "### چرا نقاط تصویری صفر است؟",
                    "",
                    "نقاط تصویری فقط وقتی ساخته می‌شوند که:",
                    "1. **در دادهٔ منبع (JSON) آدرس تصویر باشد:** فیلد `ae_multimedia_info_dto.image_urls` یا `product.itemMainPic` در فایل‌های محصولات پر باشد.",
                    "2. **دریافت و embed تصویر موفق باشد:** تابع `embed_image_url` تصویر را از URL دانلود و با CLIP بردار می‌سازد. اگر درخواست HTTP شکست بخورد (مثلاً لینک منقضی، فیلتر، قطع شبکه، یا timeout)، آن تصویر بی‌صدا رد می‌شود و نقطهٔ تصویری ساخته نمی‌شود.",
                    "",
                    "برای اطمینان: ingestion را دوباره با **لاگ فعال** اجرا کنید تا در لاگ ببینید چند محصول `image_urls` دارند و چند بار embed تصویر خطا می‌دهد.",
                    "",
                ])
            if prod_stats["price_count"] is not None:
                lines.extend([
                    "### آمار قیمت",
                    f"- کمینه: {prod_stats['price_min']}",
                    f"- بیشینه: {prod_stats['price_max']}",
                    f"- میانگین: {round(prod_stats['price_avg'], 2)}",
                    f"- تعداد نقاط دارای قیمت: {prod_stats['price_count']}",
                    "",
                ])
            if prod_stats["categories"]:
                lines.append("### توزیع بر اساس دسته‌بندی")
                lines.append("")
                for cat, cnt in sorted(prod_stats["categories"].items(), key=lambda x: -x[1]):
                    lines.append(f"- **{cat}**: {cnt} نقطه")
                lines.append("")
        except Exception as e:
            lines.append(f"- خطا در آمار تفصیلی: {e}")
            lines.append("")
    else:
        lines.append("کالکشن محصولات وجود ندارد.")
        lines.append("")

    # ——— فروشگاه ———
    lines.extend(["---", "", "## کالکشن فروشگاه (Store)", ""])
    if QDRANT_COLLECTION_STORE in all_collections:
        try:
            store_stats = stats_store(client, QDRANT_COLLECTION_STORE)
            lines.append(f"- **تعداد نقاط (فروشگاه‌ها):** {store_stats['count']}")
            if store_stats["names"]:
                lines.append("")
                lines.append("### لیست فروشگاه‌ها")
                for n in store_stats["names"]:
                    lines.append(f"- {n}")
                lines.append("")
        except Exception as e:
            lines.append(f"- خطا: {e}")
            lines.append("")
    else:
        lines.append("کالکشن فروشگاه وجود ندارد.")
        lines.append("")

    # ——— FAQ ———
    lines.extend(["---", "", "## کالکشن سوالات متداول (FAQ)", ""])
    if QDRANT_COLLECTION_FAQ in all_collections:
        try:
            faq_stats = stats_faq(client, QDRANT_COLLECTION_FAQ)
            lines.append(f"- **تعداد نقاط (سوال/جواب):** {faq_stats['count']}")
            if faq_stats.get("categories"):
                lines.append("")
                lines.append("### توزیع بر اساس دسته")
                for cat, cnt in sorted(faq_stats["categories"].items(), key=lambda x: -x[1]):
                    lines.append(f"- **{cat}**: {cnt}")
                lines.append("")
            if faq_stats.get("sample_questions"):
                lines.append("### نمونه سوالات (حداکثر ۲۰ مورد)")
                for q in faq_stats["sample_questions"][:20]:
                    lines.append(f"- {q}…" if len(q) >= 100 else f"- {q}")
                lines.append("")
        except Exception as e:
            lines.append(f"- خطا: {e}")
            lines.append("")
    else:
        lines.append("کالکشن FAQ وجود ندارد.")
        lines.append("")

    lines.extend(["---", "", "*پایان گزارش*"])
    return "\n".join(lines)


def main():
    out_dir = Path(__file__).resolve().parent.parent / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "qdrant_stats_report.md"

    print("Connecting to Qdrant and building report...")
    try:
        report_text = build_report()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

    report_path.write_text(report_text, encoding="utf-8")
    print(f"Report saved: {report_path}")
    print("(Report content is in Persian in the file.)")


if __name__ == "__main__":
    main()
