"""RAG: Qdrant search (with score threshold) + LangChain OpenRouter stream."""
import asyncio
import json
import queue
import re
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncGenerator

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, Range, MatchValue
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage

from app.config import (
    QDRANT_URL,
    QDRANT_COLLECTION,
    QDRANT_COLLECTION_STORE,
    QDRANT_COLLECTION_FAQ,
    RAG_TOP_K,
    RAG_SCORE_THRESHOLD,
    MIN_SCORE_TO_DISPLAY,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_MODEL,
)
from app.ingestion.qdrant_store import ensure_collection


def _extract_first_json_object(text: str) -> str | None:
    """Extract the first complete JSON object from text (handles nested braces)."""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def find_matching_category(category_name: str | None) -> str | None:
    """Match user/LLM category name to an exact category in the collection. Exact, then partial, then keyword synonyms."""
    if not category_name or not category_name.strip():
        return None
    data = analyze_collection_data()
    available = data.get("categories") or []
    if not available:
        return None
    lower = category_name.strip().lower()
    for c in available:
        if c.lower() == lower:
            return c
    for c in available:
        if lower in c.lower() or c.lower() in lower:
            return c
    keyword_to_terms: dict[str, list[str]] = {
        "smartphone": ["Mobile Phone", "Phone", "Mobile", "Cell Phone", "Smartphone"],
        "phone": ["Mobile Phone", "Phone", "Mobile", "Cell Phone"],
        "mobile": ["Mobile Phone", "Phone", "Mobile", "Cell Phone"],
        "cellphone": ["Mobile Phone", "Phone", "Mobile", "Cell Phone"],
        "گوشی": ["Mobile Phone", "Phone", "Mobile", "Cell Phone", "Smartphone"],
        "موبایل": ["Mobile Phone", "Phone", "Mobile", "Cell Phone"],
        "laptop": ["Computer", "Laptop", "PC", "Notebook"],
        "computer": ["Computer", "PC", "Laptop", "Notebook"],
        "pc": ["Computer", "PC", "Laptop", "Notebook"],
        "headphone": ["Audio", "Headphone", "Earphone", "Earbud"],
        "headphones": ["Audio", "Headphone", "Earphone", "Earbud"],
        "earphone": ["Audio", "Headphone", "Earphone", "Earbud"],
        "earbud": ["Audio", "Headphone", "Earphone", "Earbud"],
        "watch": ["Watch", "Smart Watch", "Smartwatch"],
        "smartwatch": ["Watch", "Smart Watch", "Smartwatch", "Smart Electronics"],
        "bag": ["Bag", "Handbag", "Bags", "Women's Bags", "Men's Bags"],
        "bags": ["Bag", "Handbag", "Bags", "Women's Bags", "Men's Bags"],
        "کیف": ["Bag", "Handbag", "Bags", "Women's Bags", "Men's Bags"],
        "clothes": ["Clothing", "Men's Clothing", "Women's Clothing", "Apparel", "Fashion"],
        "clothing": ["Clothing", "Men's Clothing", "Women's Clothing", "Apparel", "Fashion"],
        "لباس": ["Clothing", "Men's Clothing", "Women's Clothing", "Apparel", "Fashion"],
        "پوشاک": ["Clothing", "Men's Clothing", "Women's Clothing", "Apparel", "Fashion"],
    }
    for keyword, terms in keyword_to_terms.items():
        if keyword in lower:
            for term in terms:
                for c in available:
                    if term.lower() in c.lower():
                        return c
    return None


# Map negative constraint keys (from LLM) to category_name values to exclude (post-filter).
# Keys can be English or Persian; we match by substring.
NEGATIVE_CONSTRAINT_TO_CATEGORIES: dict[str, list[str]] = {
    "toys": ["Toys & Hobbies"],
    "اسباب بازی": ["Toys & Hobbies"],
    "gift card": [],
    "cash": [],
    "kitchen items": ["Home & Garden", "Kitchen"],
    "وسایل آشپزخانه": ["Home & Garden", "Kitchen"],
    "clothes": ["Men's Clothing", "Women's Clothing", "Apparel", "Fashion", "Novelty & Special Use"],
    "لباس": ["Men's Clothing", "Women's Clothing", "Apparel", "Fashion", "Novelty & Special Use"],
    "teddy": ["Toys & Hobbies"],
    "chocolate": ["Food"],
}


def _apply_negative_constraints_filter(
    search_results: list[dict],
    negative_constraints: list[str] | None,
) -> list[dict]:
    """Remove results whose category_name is in the exclude set for any of the constraint keys."""
    if not negative_constraints or not search_results:
        return search_results
    categories_to_exclude: set[str] = set()
    for key in negative_constraints:
        key_lower = (key or "").strip().lower()
        if not key_lower:
            continue
        for constraint_key, cat_list in NEGATIVE_CONSTRAINT_TO_CATEGORIES.items():
            if constraint_key in key_lower or key_lower in constraint_key:
                categories_to_exclude.update(cat_list)
    if not categories_to_exclude:
        return search_results
    out = []
    for r in search_results:
        payload = r.get("payload") or {}
        cat = (payload.get("category_name") or "").strip()
        if cat and cat in categories_to_exclude:
            continue
        out.append(r)
    return out


def analyze_collection_data() -> dict:
    """Scroll Qdrant collection and return categories list and price stats (min/max/avg/count)."""
    client = QdrantClient(url=QDRANT_URL)
    ensure_collection(client, QDRANT_COLLECTION)
    categories: set[str] = set()
    prices: list[float] = []
    offset = None
    batch_size = 1000
    while True:
        scroll_result = client.scroll(
            collection_name=QDRANT_COLLECTION,
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
            cat = payload.get("category_name")
            if cat and isinstance(cat, str) and cat.strip():
                categories.add(cat.strip())
            p = payload.get("price")
            if p is not None:
                try:
                    prices.append(float(p))
                except (TypeError, ValueError):
                    pass
        offset = next_offset
        if offset is None:
            break
    price_stats = {}
    if prices:
        price_stats = {
            "min": min(prices),
            "max": max(prices),
            "avg": sum(prices) / len(prices),
            "count": len(prices),
        }
    return {
        "categories": sorted(categories),
        "category_count": len(categories),
        "price_stats": price_stats,
        "total_products": len(prices),
    }


SYSTEM_PROMPT = """You are a helpful product assistant.

- **Language:** Always respond in the same language the user used for their message (e.g. if they ask in English, answer in English; if in Persian/Farsi, answer in Persian; if in another language, answer in that language). Do not switch language unless the user switches.
- The context below may contain three sections: "--- Store Information ---" (address, hours, contact), "--- FAQ ---" (Q&A about orders, returns, payment, delivery), and "--- Relevant Products ---". Use all provided sections to answer; e.g. for return policy use the FAQ section, for "where are you" or "store name" use Store Information.
- Use the conversation history for: the user's name, greetings, "how are you", "what's my name", and any non-product chit-chat. Remember what the user said (e.g. their name) and use it in later replies.
- For product-related questions (e.g. "find me X", "do you have Y"): answer only from the provided product context. If the context says "No relevant products found" or does not contain the product, politely say you don't have that in your catalog and suggest trying different keywords.
- When you have found products in the context: give a short reply (e.g. "Here are some options:" or "I found these products for you:") and do not list all product names in your message—product images and details are shown in cards below your message.
- When the user asks about one specific product (or "the first one", "that product"): answer only about that product. Do not suggest or mention other products unless the user asked for multiple options.
- When the user asks for details or full information about one specific product and there is only one product in the context: provide all the product information (price, category, specifications, description) in your reply. Do not suggest or mention other products.
- Do not invent product names, prices, or details. Only mention products that appear in the product context.
- When the user asked to exclude certain types (e.g. no toys, no kitchen items): recommend only products from the context that are not of those types. If all context products are of the excluded type, say politely that there are no matching options in the catalog for that constraint.
- For abstract queries ("I don't know what to buy", "popular gifts"): suggest a few varied options from the product context; keep the reply helpful and concise.
- When the user asks about the price of a specific color or variant (e.g. "how much is this color?"), use the variant price listed in the product context for that color/variant, not the base product price.
- If the user searched by image and we found similar products: reply with a short message presenting the results (e.g. "Here are similar products I found based on your image" or "I found these similar products for you."). Do NOT ask the user for more details or keywords."""

_executor = ThreadPoolExecutor(max_workers=4)


def _embed_text_sync(text: str) -> list[float]:
    from app.ingestion.clip_embedder import embed_text
    return embed_text(text)


def _embed_image_sync(image_bytes: bytes) -> list[float]:
    from app.ingestion.clip_embedder import embed_image_bytes
    return embed_image_bytes(image_bytes)


def get_query_vector(text: str | None, image_bytes: bytes | None) -> list[float]:
    """Get embedding vector for the query (text or image). Used for parallel search in store/faq."""
    if image_bytes:
        return _embed_image_sync(image_bytes)
    if text and text.strip():
        return _embed_text_sync(text.strip())
    return _embed_text_sync("")


def search_qdrant(
    query_vector: list[float],
    top_k: int = RAG_TOP_K,
    score_threshold: float = RAG_SCORE_THRESHOLD,
    price_max: float | None = None,
    category: str | None = None,
) -> list[dict]:
    """Search Qdrant; return points with score >= score_threshold. Optional filters: price_max (lte), category (exact match on category_name).
    If none, retry with 0.25 then 0 so we always return something when collection has points."""
    client = QdrantClient(url=QDRANT_URL)
    ensure_collection(client, QDRANT_COLLECTION)
    conditions = []
    if price_max is not None:
        conditions.append(FieldCondition(key="price", range=Range(lte=price_max)))
    if category is not None and category.strip():
        conditions.append(FieldCondition(key="category_name", match=MatchValue(value=category.strip())))
    query_filter = Filter(must=conditions) if conditions else None

    def _query(q_filter: Filter | None, thr: float):
        return client.query_points(
            collection_name=QDRANT_COLLECTION,
            query=query_vector,
            limit=top_k,
            score_threshold=thr,
            query_filter=q_filter,
        )

    response = _query(query_filter, score_threshold)
    points = [{"payload": r.payload, "score": r.score} for r in response.points]
    if not points and score_threshold > 0.25:
        response = _query(query_filter, 0.25)
        points = [{"payload": r.payload, "score": r.score} for r in response.points]
    if not points and score_threshold > 0.0:
        response = _query(query_filter, 0.0)
        points = [{"payload": r.payload, "score": r.score} for r in response.points]
    return points


def search_store(
    query_vector: list[float],
    top_k: int = 3,
    score_threshold: float = RAG_SCORE_THRESHOLD,
) -> list[dict]:
    """Search store collection; return points with score >= score_threshold. Fallback to lower threshold if no results (so any-language queries still match)."""
    client = QdrantClient(url=QDRANT_URL)
    ensure_collection(client, QDRANT_COLLECTION_STORE)
    for thr in (score_threshold, 0.25, 0.0):
        try:
            response = client.query_points(
                collection_name=QDRANT_COLLECTION_STORE,
                query=query_vector,
                limit=top_k,
                score_threshold=thr,
            )
            points = [{"payload": r.payload, "score": r.score} for r in response.points]
            if points:
                return points
        except Exception:
            pass
    return []


def search_faq(
    query_vector: list[float],
    top_k: int = 5,
    score_threshold: float = RAG_SCORE_THRESHOLD,
) -> list[dict]:
    """Search FAQ collection; return points with score >= score_threshold. Fallback to lower threshold if no results (so any-language queries still match)."""
    client = QdrantClient(url=QDRANT_URL)
    ensure_collection(client, QDRANT_COLLECTION_FAQ)
    for thr in (score_threshold, 0.25, 0.0):
        try:
            response = client.query_points(
                collection_name=QDRANT_COLLECTION_FAQ,
                query=query_vector,
                limit=top_k,
                score_threshold=thr,
            )
            points = [{"payload": r.payload, "score": r.score} for r in response.points]
            if points:
                return points
        except Exception:
            pass
    return []


def build_combined_context(
    store_results: list[dict],
    faq_results: list[dict],
    product_results: list[dict],
) -> str:
    """Build a single context string for the LLM with labeled sections: Store Information, FAQ, Relevant Products."""
    sections = []
    if store_results:
        parts = []
        for r in store_results:
            p = r.get("payload") or {}
            ctx = p.get("context_text") or ""
            if not ctx:
                name = p.get("name") or ""
                address = p.get("address") or ""
                phone = p.get("phone") or ""
                ctx = f"Store name / نام فروشگاه: {name}  Address / آدرس: {address}  Phone / تلفن: {phone}".strip()
            if ctx:
                parts.append(ctx)
        if parts:
            sections.append("--- Store Information ---\n" + "\n\n".join(parts))
    if faq_results:
        parts = []
        for r in faq_results:
            p = r.get("payload") or {}
            q = p.get("question") or ""
            a = p.get("answer") or ""
            if q or a:
                parts.append(f"Q: {q}\nA: {a}")
        if parts:
            sections.append("--- FAQ ---\n" + "\n\n".join(parts))
    if product_results:
        parts = []
        for i, r in enumerate(product_results, 1):
            payload = r.get("payload") or {}
            ctx = payload.get("context_text") or payload.get("subject") or ""
            if ctx:
                parts.append(f"{i}. {ctx}")
        if parts:
            sections.append("--- Relevant Products ---\n" + "\n\n".join(parts))
    if not sections:
        return "No relevant products found."
    return "\n\n".join(sections)


def filter_search_results_by_min_score(
    search_results: list[dict],
    min_score: float = MIN_SCORE_TO_DISPLAY,
) -> list[dict]:
    """Keep only results with score >= min_score. Use before build_context/products so we do not show irrelevant products when Qdrant fallback threshold (0.25/0) was used."""
    if not search_results:
        return []
    return [r for r in search_results if (r.get("score") or 0) >= min_score]


def products_from_search_results(search_results: list[dict]) -> list[dict]:
    """Build list of product summaries (unique by product_id) for frontend display."""
    products = []
    seen_ids = set()
    for r in search_results:
        p = r.get("payload") or {}
        pid = p.get("product_id")
        if pid is None or pid in seen_ids:
            continue
        seen_ids.add(pid)
        image_url = p.get("image_url")
        if not image_url and p.get("image_urls"):
            urls = p["image_urls"]
            image_url = urls[0] if isinstance(urls, list) and urls else None
        products.append({
            "product_id": pid,
            "subject": p.get("subject") or "",
            "price": p.get("price"),
            "image_url": image_url,
            "category_name": p.get("category_name") or "",
            "variants": p.get("variants") or [],
        })
    return products


def build_context(search_results: list[dict]) -> str:
    """Build context string from search results (context_text only)."""
    if not search_results:
        return "No relevant products found."
    parts = []
    for i, r in enumerate(search_results, 1):
        payload = r.get("payload") or {}
        ctx = payload.get("context_text") or payload.get("subject") or ""
        if ctx:
            parts.append(f"[{i}]\n{ctx}")
    return "\n\n".join(parts) if parts else "No relevant products found."


def get_llm():
    """ChatOpenAI configured for OpenRouter."""
    return ChatOpenAI(
        model=OPENROUTER_MODEL,
        openai_api_key=OPENROUTER_API_KEY,
        openai_api_base=OPENROUTER_BASE_URL,
        temperature=0.3,
        streaming=True,
    )


def _invoke_chain_sync(
    context: str,
    history: list,
    user_message: str,
) -> str:
    """Sync invoke; returns full response (for streaming we'll use stream)."""
    llm = get_llm()
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT + "\n\n**Product context:**\n{context}"),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{input}"),
    ])
    chain = prompt | llm
    full = ""
    for chunk in chain.stream({"context": context, "history": history, "input": user_message}):
        if hasattr(chunk, "content") and chunk.content:
            full += chunk.content
    return full


def run_rag_response(
    context: str,
    history: list,
    user_message: str,
    search_by_image: bool = False,
) -> str:
    """Generate complete LLM response (non-streaming). Returns full text."""
    llm = get_llm()
    image_note = ""
    if search_by_image and context.strip() != "No relevant products found.":
        image_note = (
            "\n\n**Note:** The user searched by image and we found similar products. "
            "Reply with a short message presenting these results (e.g. 'Here are similar products based on your image'). "
            "Do NOT ask for more details or keywords."
        )
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT + "\n\n**Product context:**\n{context}" + image_note),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{input}"),
    ])
    chain = prompt | llm
    result = chain.invoke({"context": context, "history": history, "input": user_message})
    return result.content if hasattr(result, "content") else str(result)


def _run_stream_into_queue(
    q: queue.Queue,
    context: str,
    history: list,
    user_message: str,
    search_by_image: bool = False,
) -> None:
    """Run sync chain.stream() and put each chunk into queue; put None when done."""
    llm = get_llm()
    image_note = ""
    if search_by_image and context.strip() != "No relevant products found.":
        image_note = (
            "\n\n**Note:** The user searched by image and we found similar products. "
            "Reply with a short message presenting these results (e.g. 'Here are similar products based on your image'). "
            "Do NOT ask for more details or keywords."
        )
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT + "\n\n**Product context:**\n{context}" + image_note),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{input}"),
    ])
    chain = prompt | llm
    try:
        for chunk in chain.stream({"context": context, "history": history, "input": user_message}):
            if hasattr(chunk, "content") and chunk.content:
                q.put(chunk.content)
    finally:
        q.put(None)


# Arabic script range for Persian/Arabic word-joining (letter forms)
_ARABIC_SCRIPT_RANGE = re.compile(r"[\u0600-\u06FF]$")
_CHUNK_SPACE_THEN_ARABIC = re.compile(r"^\s+[\u0600-\u06FF]+$")


def _normalize_persian_stream_chunk(accumulated: str, chunk: str) -> str:
    """Remove leading space from chunk when it would break Persian/Arabic word joining.
    LLM tokenizers often emit a leading space per token; when the previous text ends
    with an Arabic letter and the chunk is only space + Arabic letters, strip the space.
    """
    if not chunk or not chunk.strip():
        return chunk
    if not _ARABIC_SCRIPT_RANGE.search(accumulated.rstrip()):
        return chunk
    if not _CHUNK_SPACE_THEN_ARABIC.fullmatch(chunk):
        return chunk
    return chunk.lstrip()


async def stream_rag_response(
    context: str,
    history: list,
    user_message: str,
    search_by_image: bool = False,
) -> AsyncGenerator[str, None]:
    """Stream LLM response chunks: run sync stream in executor, yield from queue.
    Chunks are normalized so token-boundary spaces that break Persian/Arabic joining are removed.
    """
    q: queue.Queue = queue.Queue()
    loop = asyncio.get_event_loop()
    loop.run_in_executor(
        _executor, _run_stream_into_queue, q, context, history, user_message, search_by_image
    )
    accumulated = ""
    while True:
        chunk = await loop.run_in_executor(None, q.get)
        if chunk is None:
            break
        normalized = _normalize_persian_stream_chunk(accumulated, chunk)
        accumulated += normalized
        yield normalized


def generate_welcome(welcome_type: str, username: str | None = None) -> str:
    """Generate a short welcome message via LLM. welcome_type: 'dashboard' | 'new_chat'."""
    llm = get_llm()
    if welcome_type == "dashboard":
        prompt = (
            "The user named "
            + (username or "Guest")
            + " just entered the dashboard. Write a short, friendly welcome message in English (one or two sentences). Plain text only, no greeting prefix or signature."
        )
    else:
        prompt = (
            "The user just opened a new chat. Write a short welcome in English and suggest two or three example questions they could ask (e.g. product search) as short sentences. Plain flowing text only, no numbers or bullets."
        )
    full = ""
    for chunk in llm.stream([HumanMessage(content=prompt)]):
        if hasattr(chunk, "content") and chunk.content:
            full += chunk.content
    return full.strip() or "Welcome!"


def is_product_related_query(message: str | None) -> bool:
    """Return True if the user message is asking about products (search, buy, recommend, etc.)."""
    if not message or not message.strip():
        return False
    text = message.strip().lower()
    # Greetings/short chit-chat: do not trigger product search
    greetings = (
        "سلام", "hello", "hi", "hey", "سلامتی", "چطوری", "چطورید", "حالت چطوره",
        "what's your name", "اسم تو", "اسمت چیه", "how are you", "good morning",
        "good evening", "good night", "صبح بخیر", "عصر بخیر", "شب بخیر",
    )
    greetings_lower = [g.lower() for g in greetings]
    if text in greetings_lower or (len(text) <= 25 and any(g in text for g in greetings_lower)):
        return False
    # Product-related keywords (English + Persian)
    product_keywords = (
        "product", "products", "buy", "purchase", "price", "find", "search", "show me",
        "recommend", "looking for", "have you got", "do you have", "دارید", "داری",
        "محصول", "محصولات", "خرید", "قیمت", "پیدا کن", "جستجو", "نشان بده", "نشون بده",
        "پیشنهاد", "چه جور", "کدام", "کدوم", "چی دارید", "چی داری", "آیا دارید",
        "کالا", "کالاها", "فروش", "فروشگاه", "catalog", "catalogue", "item", "items",
    )
    return any(kw in text for kw in product_keywords)


def is_broad_products_query(message: str | None) -> bool:
    """Return True if the user is asking to see all/list all products (use low score threshold)."""
    if not message or not message.strip():
        return False
    text = message.strip().lower()
    broad_phrases = (
        "show me all", "show all", "list all", "all products", "all product",
        "همه محصولات", "لیست محصولات", "نشون بده همه", "نشان بده همه",
        "همه کالا", "لیست کالا", "everything", "show everything", "list products",
    )
    return any(phrase in text for phrase in broad_phrases)


def is_single_product_detail_query(message: str | None) -> bool:
    """Return True if the user is asking for full details of one specific product (not a list of options).
    In that case we return only the best-matching product (top_k=1) so we don't show other products.
    """
    if not message or not message.strip():
        return False
    text = message.strip().lower()
    detail_phrases = (
        "show me more details", "more details of", "details of", "detail of",
        "information about", "info about", "tell me about this product",
        "full details", "all details", "complete information",
        "اطلاعات این محصول", "جزئیات این محصول", "اطلاعات بیشتر", "جزئیات بیشتر",
        "اطلاعات محصول", "جزئیات محصول", "همه اطلاعات", "همه جزئیات",
    )
    return any(phrase in text for phrase in detail_phrases)


def run_embed_and_search(
    text: str | None,
    image_bytes: bytes | None,
    top_k: int | None = None,
    price_max: float | None = None,
    category: str | None = None,
) -> list[dict]:
    """Run embed (text or image) and Qdrant search in executor; return filtered results.
    Optional filters: price_max, category (exact match on category_name)."""
    if image_bytes:
        vector = _embed_image_sync(image_bytes)
    elif text:
        vector = _embed_text_sync(text)
    else:
        return []
    # For "show me all products" / "همه محصولات" use no score threshold so we return top_k by similarity
    score_threshold = 0.0 if is_broad_products_query(text) else RAG_SCORE_THRESHOLD
    return search_qdrant(
        vector,
        top_k=top_k or RAG_TOP_K,
        score_threshold=score_threshold,
        price_max=price_max,
        category=category,
    )


def enhanced_search_with_llm(
    user_query: str,
    limit: int = 10,
    price_max: float | None = None,
    category: str | None = None,
    last_shown_products: list[dict] | None = None,
) -> dict:
    """Use LLM to extract search intent (keywords, need_ideas, suggested_keywords, negative_constraints, etc.) then search; fallbacks if no results. Returns { query, results, summary, filters_applied }."""
    if not OPENROUTER_API_KEY:
        results = run_embed_and_search(user_query, None, top_k=limit, price_max=price_max, category=category)
        return {
            "query": user_query,
            "results": results,
            "summary": None,
            "filters_applied": {"price_max": price_max, "category": category},
        }
    analysis = analyze_collection_data()
    available_categories = (analysis.get("categories") or [])[:30]
    categories_context = ", ".join(available_categories) if available_categories else "No categories available"

    # Build minimal context for "last shown products" (title + id only, same order as frontend)
    last_products_block = ""
    if last_shown_products:
        lines = []
        for i, p in enumerate(last_shown_products, 1):
            subj = (p.get("subject") or "").strip() or "(no title)"
            pid = p.get("product_id")
            lines.append(f"  {i}. [{pid}] {subj}")
        last_products_block = (
            "\n\nRecently shown products (same order as displayed; use these names when user says 'this product', 'the first one', 'that one', etc.):\n"
            + "\n".join(lines)
        )

    prompt = f"""Analyze this product search query and respond with a single JSON object. Use only the schema below.

**Schema (all fields required; use null or empty array where not applicable):**
- keywords: string (English search terms matching the catalog; if user wants ideas for an occasion/relation, still add base terms)
- price_max: number | null (max price filter only if user explicitly mentions price)
- category: string | null (MUST be one of the available categories below, or null)
- relation_or_occasion: string | null (e.g. "spouse birthday", "Mother's Day", "boss", "housewarming")
- interests: string | null (e.g. "tech gadgets", "coffee", "gaming", "outdoor")
- negative_constraints: array of strings (things user does NOT want, e.g. ["toys"], ["kitchen items"], ["clothes"])
- need_ideas: boolean (true if user asks for suggestions / "what to get" / "don't know what to buy" for an occasion/relation)
- suggested_keywords: string | null (when need_ideas is true, provide concrete product-type keywords in English for that occasion/relation, e.g. "jewelry perfume smartwatch romantic" for spouse gift; otherwise null)

Available categories (use exactly as written or null): {categories_context}
{last_products_block}

**Examples:**

Example 1 – Direct query:
Query: "گوشی آیفون"
Response: {{"keywords": "iphone smartphone", "price_max": null, "category": null, "relation_or_occasion": null, "interests": null, "negative_constraints": [], "need_ideas": false, "suggested_keywords": null}}

Example 2 – Needs ideas:
Query: "کادو تولد همسر چی بگیرم"
Response: {{"keywords": "gift birthday spouse", "price_max": null, "category": null, "relation_or_occasion": "spouse birthday", "interests": null, "negative_constraints": [], "need_ideas": true, "suggested_keywords": "jewelry perfume smartwatch romantic gift"}}

Example 3 – With negative constraint:
Query: "کادو برای بچه ولی اسباب بازی نباشه"
Response: {{"keywords": "gift kids children", "price_max": null, "category": null, "relation_or_occasion": null, "interests": null, "negative_constraints": ["toys"], "need_ideas": true, "suggested_keywords": "books educational clothes shoes"}}

Query: "{user_query}"

Respond with JSON only, no other text."""

    search_text = user_query
    negative_constraints: list[str] = []
    try:
        llm = get_llm()
        response = llm.invoke([HumanMessage(content=prompt)])
        content = (response.content or "").strip()
        json_str = _extract_first_json_object(content)
        if json_str:
            parsed = json.loads(json_str)
            base_keywords = (parsed.get("keywords") or "").strip() or user_query
            need_ideas = parsed.get("need_ideas") is True
            suggested = (parsed.get("suggested_keywords") or "").strip()
            if need_ideas and suggested:
                search_text = suggested
            else:
                search_text = base_keywords
            if price_max is None and parsed.get("price_max") is not None:
                try:
                    price_max = float(parsed["price_max"])
                except (TypeError, ValueError):
                    pass
            if category is None and parsed.get("category"):
                category = parsed.get("category")
            raw_neg = parsed.get("negative_constraints")
            if isinstance(raw_neg, list):
                negative_constraints = [str(x).strip() for x in raw_neg if x]
            elif isinstance(raw_neg, str) and raw_neg:
                negative_constraints = [raw_neg.strip()]
        else:
            parsed = {}
    except Exception:
        parsed = {}
        negative_constraints = []

    if category:
        matched = find_matching_category(category)
        category = matched if matched else None

    results = run_embed_and_search(search_text, None, top_k=limit, price_max=price_max, category=category)
    if not results and (category or price_max):
        results = run_embed_and_search(search_text, None, top_k=limit, price_max=price_max, category=None)
    if not results and (category or price_max):
        results = run_embed_and_search(search_text, None, top_k=limit, price_max=None, category=category)
    if not results:
        results = run_embed_and_search(search_text, None, top_k=limit, price_max=None, category=None)
    if not results and search_text != user_query:
        results = run_embed_and_search(user_query, None, top_k=limit, price_max=None, category=None)

    results = _apply_negative_constraints_filter(results, negative_constraints)

    summary = None
    if results and OPENROUTER_API_KEY:
        try:
            llm = get_llm()
            lines = "\n".join(
                f"- {r.get('payload', {}).get('subject', 'Unknown')} (${r.get('payload', {}).get('price', 0):.2f}, {r.get('payload', {}).get('category_name', '')})"
                for r in results[:5]
            )
            summary_prompt = f'Based on the search query "{user_query}", I found these products:\n{lines}\n\nProvide a brief, helpful summary (2-3 sentences) about these search results.'
            summary_response = llm.invoke([HumanMessage(content=summary_prompt)])
            summary = (summary_response.content or "").strip()
        except Exception:
            pass
    return {
        "query": user_query,
        "results": results,
        "summary": summary,
        "filters_applied": {"price_max": price_max, "category": category, "negative_constraints": negative_constraints},
    }
