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
    BASE_URL,
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


def _apply_exclude_terms_filter(
    search_results: list[dict],
    exclude_terms: list[str] | None,
) -> list[dict]:
    """Remove results whose product title/subject contains any of the exclude terms.
    
    This is a title-level filter (different from negative_constraints which is category-level).
    Used to filter out products for the wrong audience, e.g. men's products for a female recipient.
    """
    if not exclude_terms or not search_results:
        return search_results
    
    # Normalize exclude terms
    normalized_terms = [t.lower().strip() for t in exclude_terms if t and t.strip()]
    if not normalized_terms:
        return search_results
    
    out = []
    for r in search_results:
        payload = r.get("payload") or {}
        subject = (payload.get("subject") or "").lower()
        category = (payload.get("category_name") or "").lower()
        # Check if product title or category contains any exclude term
        should_exclude = False
        for term in normalized_terms:
            # Check subject (product title)
            if term in subject:
                should_exclude = True
                break
            # Also check category name for gendered categories like "Men's Clothing"
            if term in category:
                should_exclude = True
                break
        if not should_exclude:
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


SYSTEM_PROMPT = """You are PARAK (پَرَک), an intelligent assistant (دستیار هوشمند). You help users with product search, store information, and FAQ; be friendly, accurate, and concise.

- **Language:** Always respond in the same language the user used for their message (e.g. if they ask in English, answer in English; if in Persian/Farsi, answer in Persian; if in another language, answer in that language). Do not switch language unless the user switches.
- The context below may contain three sections: "--- Store Information ---" (address, hours, contact), "--- FAQ ---" (Q&A about orders, returns, payment, delivery), and "--- Relevant Products ---". Use all provided sections to answer; e.g. for return policy use the FAQ section, for "where are you" or "store name" use Store Information.
- Use the conversation history for: the user's name, greetings, "how are you", "what's my name", and any non-product chit-chat. Remember what the user said (e.g. their name) and use it in later replies.
- For product-related questions (e.g. "find me X", "do you have Y"): answer only from the provided product context. If the context says "No relevant products found" or does not contain the product, politely say you don't have that in your catalog and suggest trying different keywords.
- **CRITICAL — Relevance filtering:** When presenting products, ONLY mention products that are genuinely relevant to the user's specific request. Consider the recipient's gender, age, interests, and stated preferences:
  - If the user asks for a gift for a **female** (girlfriend, wife, mother, sister): SKIP any product clearly intended for men (e.g. "Men Watch", "Men's Wallet", "Boy's Shirt"). Only present women's or unisex products.
  - If the user asks for a gift for a **male** (boyfriend, husband, father, brother): SKIP any product clearly intended for women (e.g. "Women Dress", "Ladies Handbag", "Girl's Necklace"). Only present men's or unisex products.
  - If the user mentions a **specific hobby or interest** (e.g. hiking, cooking, gaming): ONLY present products related to that hobby. SKIP unrelated items even if they appear in the context.
  - If after filtering you have very few relevant products, present those few and say "These are the options I found in our catalog that match your criteria." Do NOT pad with irrelevant products.
- When you have found products in the context: give a short reply and recommend only 3-4 options by name. The same number of product cards is shown below your message (typically 3), so keep your suggestions to 3-4 items so the text and the cards match. Do not list more than 3 product names.
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


def detect_intent_with_llm(message: str | None) -> dict:
    """
    Use LLM to detect user intent. Returns dict with:
    - needs_qdrant_search: bool (True if product/store/faq search needed)
    - intent_type: str ("product_search" | "store_info" | "faq" | "chitchat" | "greeting" | "unknown")
    - confidence: float (0-1)
    
    This replaces keyword-based is_product_related_query with LLM understanding.
    Works for any language without hardcoded keywords.
    """
    if not message or not message.strip():
        return {"needs_qdrant_search": False, "intent_type": "unknown", "confidence": 1.0}
    
    if not OPENROUTER_API_KEY:
        # Fallback: if no API key, assume product search for non-trivial messages
        return {"needs_qdrant_search": len(message.strip()) > 10, "intent_type": "unknown", "confidence": 0.5}
    
    prompt = f"""Analyze this user message and determine the intent. Respond with ONLY a JSON object.

User message: "{message}"

Determine:
1. Does this message require searching a product database/catalog? (e.g. looking for products, asking about items, prices, recommendations)
2. Does this message require searching store information? (e.g. store hours, location, contact)
3. Does this message require searching FAQ? (e.g. return policy, shipping, payment methods)
4. Is this just a greeting or chitchat? (e.g. hello, how are you, what's your name)

Respond with this exact JSON schema:
{{
  "needs_qdrant_search": true/false,
  "intent_type": "product_search" | "store_info" | "faq" | "chitchat" | "greeting" | "unknown",
  "confidence": 0.0-1.0
}}

Rules:
- needs_qdrant_search = true if intent_type is "product_search", "store_info", or "faq"
- needs_qdrant_search = false if intent_type is "chitchat" or "greeting"
- For ambiguous messages, lean towards needs_qdrant_search = true
- Works for ANY language (English, Persian, French, Chinese, etc.)"""

    try:
        llm = ChatOpenAI(**_openrouter_chat_kwargs(temperature=0, max_tokens=150))
        response = llm.invoke([HumanMessage(content=prompt)])
        content = response.content if hasattr(response, "content") else str(response)
        
        json_str = _extract_first_json_object(content)
        if json_str:
            data = json.loads(json_str)
            return {
                "needs_qdrant_search": bool(data.get("needs_qdrant_search", False)),
                "intent_type": data.get("intent_type", "unknown"),
                "confidence": float(data.get("confidence", 0.5)),
            }
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("detect_intent LLM failed, using fallback: %s", e)
    
    # Fallback on error: assume search needed for longer messages
    return {"needs_qdrant_search": len(message.strip()) > 15, "intent_type": "unknown", "confidence": 0.3}


ALLOWED_EMOTIONS = frozenset({
    "neutral", "happy", "excited", "sad", "confused", "surprised", "love", "worried",
})


def detect_emotion_with_llm(user_message: str | None, assistant_reply: str | None) -> str | None:
    """
    Use LLM to suggest an avatar emotion based on the user message and assistant reply.
    Returns one of: neutral, happy, excited, sad, confused, surprised, love, worried.
    Returns None on failure or invalid response. (annoyed/angry are frontend-only.)
    """
    if not user_message or not user_message.strip():
        return "neutral"
    if not OPENROUTER_API_KEY:
        return None
    prompt = f"""Based on this conversation, choose the assistant avatar's emotion.

User message: "{user_message[:500]}"

Assistant reply (excerpt): "{ (assistant_reply or "")[:300] }"

Pick the most fitting emotion for the assistant's face:
- neutral: default, no strong sentiment
- happy: user thanked, praised, or expressed satisfaction (thanks, great, perfect, ممنون, عالی)
- excited: user is enthusiastic or asking for recommendations
- sad: user expressed disappointment, said answer was wrong or not helpful
- confused: user question was ambiguous or the reply might not fully match
- surprised: user asked something unusual or reacted with surprise
- love: user expressed strong affection or "you're the best"
- worried: user asked for help, urgent, or has a problem (help, urgent, مشکل, کمک)

Respond with ONLY a JSON object: {{ "emotion": "one_word_from_above" }}
Use lowercase. No other text."""

    try:
        llm = ChatOpenAI(**_openrouter_chat_kwargs(temperature=0, max_tokens=80))
        response = llm.invoke([HumanMessage(content=prompt)])
        content = response.content if hasattr(response, "content") else str(response)
        json_str = _extract_first_json_object(content)
        if not json_str:
            return None
        data = json.loads(json_str)
        emotion = (data.get("emotion") or "").strip().lower()
        if emotion in ALLOWED_EMOTIONS:
            return emotion
        return None
    except Exception:
        return None


def detect_language_with_llm(text: str | None) -> str:
    """
    Use LLM to detect the language of the given text. Returns ISO 639-1 code (e.g. 'en', 'fa', 'ar', 'zh-cn').
    Used for read-aloud to pick the appropriate TTS voice. Works for any language.
    """
    if not text or not text.strip():
        return "en"
    if len(text.strip()) < 3:
        return "en"
    if not OPENROUTER_API_KEY:
        return "en"
    prompt = f"""Determine the language of the following text. Reply with ONLY a single language code (ISO 639-1), e.g. en, fa, ar, fr, de, zh-cn, zh-tw, tr, es, ru.
Use lowercase. For Chinese use zh-cn or zh-tw. No explanation, no quotes, no punctuation.

Text:
{text[:4000]}

Language code:"""
    try:
        llm = ChatOpenAI(**_openrouter_chat_kwargs(temperature=0, max_tokens=10))
        response = llm.invoke([HumanMessage(content=prompt)])
        content = (response.content if hasattr(response, "content") else str(response)).strip().lower()
        # Extract first word/token (in case LLM added something)
        code = re.split(r"[\s,.\n]+", content)[0] if content else ""
        if code and len(code) >= 2 and code.isalpha():
            if code.startswith("zh"):
                return code if code in ("zh-cn", "zh-tw") else "zh-cn"
            return code[:10]  # cap length for safety
    except Exception:
        pass
    return "en"


# Allowed avatar emotions (must match frontend AIAvatarEmotion)
AVATAR_EMOTIONS = ("neutral", "happy", "excited", "sad", "confused", "surprised", "love", "annoyed", "angry")


def detect_emotion_with_llm(user_message: str, assistant_message: str) -> str:
    """
    Use LLM to suggest avatar emotion from the last exchange.
    Input: user message and assistant reply.
    Returns one of: neutral, happy, excited, sad, confused, surprised, love, annoyed, angry.
    Used so the avatar reacts intelligently (e.g. thankful user -> happy, frustrated -> sad/annoyed).
    """
    if not OPENROUTER_API_KEY:
        return "neutral"
    user = (user_message or "").strip()[:2000]
    assistant = (assistant_message or "").strip()[:1500]
    if not user:
        return "neutral"

    prompt = f"""You are an emotion classifier for a chat assistant's avatar. Given the user's message and the assistant's reply, choose the single most appropriate avatar emotion. You must output exactly ONE word from the list at the end.

User message:
{user}

Assistant reply (first part):
{assistant}

--- DEFINITIONS (pick the best match) ---

1) love — Use when the user expresses *personal affection or strong praise of the assistant itself* (not just "good answer"). Examples: "تو بهترینی", "عاشقتم", "دوستت دارم", "بهترین دستیاری", "you're the best", "I love you", "خیلی دوستت دارم", "ممنون که هستی", "بدون تو نمی‌تونستم". The focus is on the relationship or the assistant as a person. If the user only said "ممنون" or "عالی" without praising the assistant personally -> do NOT use love.

2) happy — Use when the user expresses *simple gratitude or satisfaction with the answer/task* (thank you, good, perfect, it worked). Examples: "ممنون", "عالی", "مرسی", "خوب بود", "درست شد", "thanks", "great", "perfect", "helpful". No strong affection, no request for suggestions. Just "I'm satisfied with what you did". If they also praised the assistant as a person (best, love you) -> use love instead. If they are asking what to do next or for recommendations -> use excited instead.

3) excited — Use when the user is *enthusiastic about doing something or actively asking for ideas/suggestions/recommendations*. Examples: "یه رستوران خوب پیشنهاد بده", "چی پیشنهاد می‌کنی؟", "می‌خوام برم سفر کجا برم؟", "recommend something", "what do you suggest?", "کدوم رو بخرم؟", "چند تا گزینه بده". The conversation is forward-looking: user wants options, ideas, or next steps. Do NOT use excited for simple "thanks" or "great" — use happy. Do NOT use excited for "you're the best" — use love.

4) neutral — Normal factual question/answer, greeting, or no strong sentiment. "سلام", "امروز هوا چطوره", "چند تا دو دو تا می‌شه".

5) sad — User said the answer was wrong, not helpful, or expressed disappointment. "جوابت اشتباه بود", "به درد من نخورد", "متاسفم ولی..."

6) annoyed — User is frustrated or impatient with the assistant. "چرا جواب نمیدی", "دوباره اشتباه گفتی".

7) angry — User is clearly angry or rude.

8) confused — ONLY when the *question* is vague or ambiguous, or the assistant clearly didn't understand. "اون چیز رو بگو", "چطور می‌تونم؟" (no context). NOT for unusual or fun questions.

9) surprised — When something *unexpected or unusual*: weird/fun question, user said "وای!" or "realmente?", or topic is funny. Unusual question -> surprised; vague question -> confused.

--- PRIORITY when both could apply ---
- "ممنون تو بهترینی" or thanks + personal praise -> love (not happy).
- "عالی ممنون" or just thanks/satisfaction -> happy (not love, not excited).
- "پیشنهاد بده" or "چی پیشنهاد می‌کنی" -> excited (not happy).
- Simple thanks after a recommendation -> happy (not excited).

Respond with ONLY one word from this exact list: neutral, happy, excited, sad, confused, surprised, love, annoyed, angry
No explanation, no quotes, no other text."""

    try:
        llm = ChatOpenAI(**_openrouter_chat_kwargs(temperature=0, max_tokens=20))
        response = llm.invoke([HumanMessage(content=prompt)])
        content = (response.content if hasattr(response, "content") else str(response)).strip().lower()
        # Take first token that is a valid emotion
        for token in re.split(r"[\s,.\n]+", content):
            if token in AVATAR_EMOTIONS:
                return token
    except Exception:
        pass
    return "neutral"


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
        image_url = p.get("main_image_url") or p.get("image_url")
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


def reorder_products_by_mention(llm_text: str, products: list[dict]) -> list[dict]:
    """Reorder product list so that products mentioned in the LLM response text
    come first (in the order they appear in the text), followed by products
    not mentioned (keeping their original relative order).
    
    This ensures the product cards displayed below the chat match the order
    the assistant described them in the text.
    """
    if not llm_text or not products:
        return products
    
    text_lower = llm_text.lower()
    
    # For each product, find the earliest position of its title in the text.
    # We try multiple matching strategies for robustness:
    # 1. Full subject match
    # 2. First N significant words of subject (handles truncated mentions)
    mentioned: list[tuple[int, int, dict]] = []  # (position_in_text, original_index, product)
    not_mentioned: list[tuple[int, dict]] = []   # (original_index, product)
    
    for idx, product in enumerate(products):
        subject = (product.get("subject") or "").strip()
        if not subject:
            not_mentioned.append((idx, product))
            continue
        
        subject_lower = subject.lower()
        best_pos = -1
        
        # Strategy 1: Find the full subject in text
        pos = text_lower.find(subject_lower)
        if pos >= 0:
            best_pos = pos
        
        # Strategy 2: Try first 5-8 significant words (LLM often abbreviates product names)
        if best_pos < 0:
            words = [w for w in subject_lower.split() if len(w) > 2]
            # Try decreasing window sizes: 8, 6, 5, 4 words
            for window in (8, 6, 5, 4):
                if len(words) >= window:
                    fragment = " ".join(words[:window])
                    pos = text_lower.find(fragment)
                    if pos >= 0:
                        best_pos = pos
                        break
        
        # Strategy 3: Try matching distinctive words (words > 4 chars, first 3)
        if best_pos < 0:
            distinctive = [w for w in subject_lower.split() if len(w) > 4][:3]
            if len(distinctive) >= 2:
                # Check if at least 2 distinctive words appear near each other in the text
                positions_found = []
                for dw in distinctive:
                    dpos = text_lower.find(dw)
                    if dpos >= 0:
                        positions_found.append(dpos)
                # If at least 2 words found within 200 chars of each other, consider it a match
                if len(positions_found) >= 2:
                    positions_found.sort()
                    if positions_found[-1] - positions_found[0] < 200:
                        best_pos = positions_found[0]
        
        if best_pos >= 0:
            mentioned.append((best_pos, idx, product))
        else:
            not_mentioned.append((idx, product))
    
    # Sort mentioned products by their position in the text (earliest first)
    mentioned.sort(key=lambda x: x[0])
    
    # Build final list: mentioned first (in text order), then not-mentioned (in original order)
    result = [item[2] for item in mentioned]
    result.extend(item[1] for item in not_mentioned)
    return result


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


def _openrouter_chat_kwargs(**extra) -> dict:
    """Shared ChatOpenAI kwargs for OpenRouter (incl. recommended headers)."""
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY is not set in backend/.env")
    kwargs: dict = {
        "model": OPENROUTER_MODEL,
        "api_key": OPENROUTER_API_KEY,
        "base_url": OPENROUTER_BASE_URL,
        **extra,
    }
    if BASE_URL:
        kwargs["default_headers"] = {
            "HTTP-Referer": BASE_URL.rstrip("/"),
            "X-Title": "RAG Shop Assistant",
        }
    return kwargs


def get_llm():
    """ChatOpenAI configured for OpenRouter."""
    return ChatOpenAI(**_openrouter_chat_kwargs(temperature=0.3, streaming=True))


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


def _compute_keyword_relevance(payload: dict, keywords: list[str]) -> tuple[float, bool]:
    """Compute relevance score based on keyword matches in product data.
    
    Checks multiple fields: subject, category_name, context_text
    Returns a tuple of (relevance_score, has_primary_match).
    - relevance_score: 0 to ~2 (can exceed 1 with bonuses)
    - has_primary_match: True if at least one of the top 3 keywords matched in subject
    """
    if not payload or not keywords:
        return 0.0, False
    
    # Gather all searchable text from product
    subject = (payload.get("subject") or "").lower()
    category = (payload.get("category_name") or "").lower()
    context = (payload.get("context_text") or "").lower()
    
    matches = 0.0
    total_weight = 0.0
    has_primary_match = False
    
    for i, kw in enumerate(keywords):
        kw_lower = kw.lower().strip()
        if not kw_lower:
            continue
        
        # Earlier keywords are more important (harmonic weight)
        weight = 1.0 / (i + 1)
        total_weight += weight
        
        # Check for match in subject (most important)
        if kw_lower in subject:
            matches += weight * 1.5  # Strong bonus for subject match
            
            # Track if primary keywords (top 3) match in subject
            if i < 3:
                has_primary_match = True
            
            # Extra bonus for exact word match in subject
            subject_words = subject.split()
            if kw_lower in subject_words:
                matches += weight * 0.5
        
        # Check for match in category
        elif kw_lower in category:
            matches += weight * 0.8
            if i < 3:
                has_primary_match = True
        
        # Check for match in context (weaker signal)
        elif kw_lower in context:
            matches += weight * 0.3
    
    relevance = matches / total_weight if total_weight > 0 else 0.0
    return relevance, has_primary_match


def _rerank_results(
    results: list[dict],
    primary_keywords: list[str],
    boost_weight: float = 0.5,
    require_keyword_match: bool = False,
) -> list[dict]:
    """Re-rank search results by combining semantic score with keyword relevance.
    
    Args:
        results: List of search results with 'payload' and 'score' keys
        primary_keywords: Keywords to look for in products (ordered by importance)
        boost_weight: How much to weight keyword matching (0-1). Higher = more keyword influence.
        require_keyword_match: If True, filter out results that don't match any primary keyword
    
    Returns:
        Re-ranked list of results with updated scores
    """
    if not results:
        return results
    
    if not primary_keywords:
        # No keywords to boost, just return sorted by original score
        return sorted(results, key=lambda x: x.get("score", 0), reverse=True)
    
    scored_results = []
    for r in results:
        payload = r.get("payload") or {}
        original_score = r.get("score") or 0.0
        
        # Compute keyword relevance
        keyword_relevance, has_primary_match = _compute_keyword_relevance(payload, primary_keywords)
        
        # Skip results without primary keyword match if required
        if require_keyword_match and not has_primary_match:
            continue
        
        # Combined score formula:
        # final = original * (1 + relevance * boost_weight)
        # This preserves semantic ordering while boosting keyword matches
        final_score = original_score * (1 + keyword_relevance * boost_weight)
        
        # Additional boost for items with primary keyword match
        if has_primary_match:
            final_score *= 1.2
        
        scored_results.append({
            **r,
            "original_score": original_score,
            "keyword_relevance": keyword_relevance,
            "has_primary_match": has_primary_match,
            "score": final_score,
        })
    
    # Sort by final score descending
    scored_results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return scored_results


def _multi_query_search(
    queries: list[str],
    top_k_per_query: int = 10,
    price_max: float | None = None,
    category: str | None = None,
    min_score: float = 0.35,
) -> list[dict]:
    """Execute multiple search queries and merge results with per-query quality filtering.
    
    For complex queries like "gift for mother", we search for multiple product types
    (perfume, jewelry, watch, etc.) and merge the results.
    
    Args:
        queries: List of search query strings
        top_k_per_query: Number of results per query
        price_max: Optional price filter
        category: Optional category filter
        min_score: Minimum semantic score per result (filters low-quality matches)
    
    Returns:
        Merged, deduplicated, and sorted results
    """
    if not queries:
        return []
    
    all_results: list[dict] = []
    seen_product_ids: set = set()
    
    for query in queries:
        results = run_embed_and_search(
            query, None,
            top_k=top_k_per_query,
            price_max=price_max,
            category=category,
        )
        
        # Extract keywords from this specific query for per-query relevance boost
        query_words = [w.lower().strip() for w in query.split() if len(w) > 2]
        
        for r in results:
            payload = r.get("payload") or {}
            pid = payload.get("product_id")
            
            # Deduplicate by product_id
            if pid is not None and pid in seen_product_ids:
                continue
            
            # Skip very low scoring results
            if (r.get("score") or 0) < min_score:
                continue
            
            if pid is not None:
                seen_product_ids.add(pid)
            
            # Tag the result with which query found it (for debugging)
            r["_source_query"] = query
            all_results.append(r)
    
    # Sort merged results by score descending
    all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return all_results


def enhanced_search_with_llm(
    user_query: str,
    limit: int = 10,
    price_max: float | None = None,
    category: str | None = None,
    last_shown_products: list[dict] | None = None,
) -> dict:
    """
    Intelligent product search using LLM for query understanding and multi-strategy search.
    
    This function:
    1. Uses LLM to understand user intent and extract search parameters
    2. For simple queries: single semantic search with keyword re-ranking
    3. For complex queries (gifts, ideas): multi-query search across product categories
    4. Re-ranks all results based on keyword relevance
    
    Returns: { query, results, summary, filters_applied }
    """
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

    # Build minimal context for "last shown products"
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

    # Enhanced prompt with multi-query support
    prompt = f"""Analyze this product search query and respond with a single JSON object.

**Schema (all fields required; use null or empty array where not applicable):**
- query_type: string ("direct" for specific product search, "exploratory" for gift/idea/recommendation queries)
- target_audience: string | null (who the product is for: "women", "men", "girls", "boys", "children", "unisex", or null if not specified)
- search_queries: array of strings (English search queries to execute. IMPORTANT: include audience-specific terms in each query, e.g. "women" or "men". For direct queries, use 1-2 queries. For exploratory queries like gifts, use 3-5 specific product type queries)
- primary_keywords: array of strings (keywords that MUST appear in relevant product titles, ordered by importance. Include gender/audience terms like "women", "ladies", "female" when the recipient is female, or "men", "male" when male)
- exclude_terms: array of strings (words that should NOT appear in product titles. E.g. for a female recipient, exclude ["men", "men's", "male", "boy", "boys"]. For a male recipient, exclude ["women", "women's", "female", "girl", "girls", "ladies"]. For hobby-specific queries, exclude unrelated product types)
- price_max: number | null (only if user explicitly mentions price)
- category: string | null (one of the available categories, or null)
- negative_constraints: array of strings (product categories/types the user does NOT want)

Available categories: {categories_context}
{last_products_block}

**Critical Rules:**
1. ALWAYS set target_audience when the recipient's gender or age is clear from context (girlfriend/wife/mother → "women", boyfriend/husband/father → "men", daughter → "girls", son → "boys")
2. ALWAYS populate exclude_terms to filter out products meant for the WRONG audience (e.g. men's products for a female recipient)
3. search_queries MUST be specific and targeted. Include the audience in the query text (e.g. "women watch elegant" not just "watch elegant")
4. For hobby/interest-based queries, search_queries should focus ONLY on that hobby (e.g. hiking → outdoor/camping gear, NOT random items)

**Examples:**

Example 1 – Direct product query:
Query: "قاب گوشی"
Response: {{"query_type": "direct", "target_audience": null, "search_queries": ["phone case cover protective"], "primary_keywords": ["case", "cover", "phone case", "protective"], "exclude_terms": [], "price_max": null, "category": null, "negative_constraints": []}}

Example 2 – Birthday gift for girlfriend:
Query: "برای دوست دخترم میخوام کادوی تولد بگیرم"
Response: {{"query_type": "exploratory", "target_audience": "women", "search_queries": ["women perfume fragrance gift", "women jewelry necklace bracelet ring", "women skincare beauty cream set", "women watch elegant ladies", "women handbag purse fashion"], "primary_keywords": ["women", "ladies", "female", "perfume", "jewelry", "necklace", "skincare", "beauty", "watch", "handbag", "gift"], "exclude_terms": ["men", "men's", "male", "boy", "boys", "masculine"], "price_max": null, "category": null, "negative_constraints": []}}

Example 3 – Gift for father who likes hiking:
Query: "برای پدرم که به کوهنوردی علاقه داره کادو میخوام"
Response: {{"query_type": "exploratory", "target_audience": "men", "search_queries": ["hiking backpack outdoor mountaineering", "camping equipment tent sleeping bag", "hiking boots shoes outdoor trekking", "outdoor sports water bottle thermos", "hiking flashlight headlamp camping gear"], "primary_keywords": ["hiking", "outdoor", "camping", "trekking", "mountaineering", "backpack", "boots", "sports"], "exclude_terms": ["women", "women's", "female", "girl", "girls", "ladies", "baby", "kids", "pencil", "stationery", "kitchen"], "price_max": null, "category": null, "negative_constraints": []}}

Example 4 – Gift for mother:
Query: "کادو برای مادر" or "هدیه روز مادر"
Response: {{"query_type": "exploratory", "target_audience": "women", "search_queries": ["women perfume fragrance elegant scent", "women jewelry necklace bracelet ring gold", "women skincare beauty cream anti-aging serum", "women scarf shawl fashion silk", "women watch elegant ladies classic"], "primary_keywords": ["women", "ladies", "perfume", "fragrance", "jewelry", "necklace", "skincare", "beauty", "watch", "scarf", "gift"], "exclude_terms": ["men", "men's", "male", "boy", "boys"], "price_max": null, "category": null, "negative_constraints": []}}

Example 5 – Gift for child (no toys):
Query: "کادو برای بچه ولی اسباب بازی نباشه"
Response: {{"query_type": "exploratory", "target_audience": "children", "search_queries": ["children books educational learning", "kids clothes fashion cute", "school supplies stationery set", "children shoes sneakers colorful"], "primary_keywords": ["kids", "children", "educational", "books", "clothes", "school", "child"], "exclude_terms": [], "price_max": null, "category": null, "negative_constraints": ["toys", "toy", "game", "doll", "puzzle"]}}

Example 6 – Bluetooth headphones:
Query: "هدفون بلوتوث"
Response: {{"query_type": "direct", "target_audience": null, "search_queries": ["bluetooth headphone wireless earphone"], "primary_keywords": ["headphone", "earphone", "headset", "earbuds", "bluetooth", "wireless"], "exclude_terms": [], "price_max": null, "category": null, "negative_constraints": []}}

Example 7 – Gift for husband/boyfriend:
Query: "کادو تولد همسرم (آقا)"
Response: {{"query_type": "exploratory", "target_audience": "men", "search_queries": ["men cologne perfume fragrance", "men watch smartwatch elegant", "men wallet leather accessories", "men belt leather fashion", "men sunglasses fashion sport"], "primary_keywords": ["men", "male", "cologne", "watch", "wallet", "belt", "sunglasses", "leather"], "exclude_terms": ["women", "women's", "female", "girl", "girls", "ladies", "lipstick", "dress"], "price_max": null, "category": null, "negative_constraints": []}}

Query: "{user_query}"

Respond with JSON only, no other text."""

    # Default values
    search_queries: list[str] = [user_query]
    primary_keywords: list[str] = []
    negative_constraints: list[str] = []
    exclude_terms: list[str] = []
    target_audience: str | None = None
    query_type = "direct"
    
    try:
        llm = get_llm()
        response = llm.invoke([HumanMessage(content=prompt)])
        content = (response.content or "").strip()
        json_str = _extract_first_json_object(content)
        
        if json_str:
            parsed = json.loads(json_str)
            
            # Extract query type
            query_type = parsed.get("query_type", "direct")
            
            # Extract target audience
            target_audience = parsed.get("target_audience")
            
            # Extract search queries
            raw_queries = parsed.get("search_queries")
            if isinstance(raw_queries, list) and raw_queries:
                search_queries = [str(q).strip() for q in raw_queries if q and str(q).strip()]
            
            # Extract primary keywords
            raw_primary = parsed.get("primary_keywords")
            if isinstance(raw_primary, list):
                primary_keywords = [str(k).strip() for k in raw_primary if k and str(k).strip()]
            
            # Extract exclude_terms (words that must NOT appear in product titles)
            raw_exclude = parsed.get("exclude_terms")
            if isinstance(raw_exclude, list):
                exclude_terms = [str(x).strip().lower() for x in raw_exclude if x and str(x).strip()]
            elif isinstance(raw_exclude, str) and raw_exclude:
                exclude_terms = [raw_exclude.strip().lower()]
            
            # Extract price filter
            if price_max is None and parsed.get("price_max") is not None:
                try:
                    price_max = float(parsed["price_max"])
                except (TypeError, ValueError):
                    pass
            
            # Extract category
            if category is None and parsed.get("category"):
                category = parsed.get("category")
            
            # Extract negative constraints
            raw_neg = parsed.get("negative_constraints")
            if isinstance(raw_neg, list):
                negative_constraints = [str(x).strip() for x in raw_neg if x]
            elif isinstance(raw_neg, str) and raw_neg:
                negative_constraints = [raw_neg.strip()]
        else:
            parsed = {}
    except Exception:
        parsed = {}
        search_queries = [user_query]

    # Auto-expand exclude_terms based on target_audience
    # When the recipient is an adult, auto-exclude children's product terms
    if target_audience in ("men", "women"):
        adult_auto_exclude = {"children", "child", "toddler", "infant", "baby", "kid", "kids"}
        existing = set(exclude_terms)
        for term in adult_auto_exclude:
            if term not in existing:
                exclude_terms.append(term)
    # When target is men, ensure women terms are excluded and vice versa
    if target_audience == "women":
        women_auto_exclude = {"men", "men's", "male", "boy", "boys", "masculine", "husband"}
        existing = set(exclude_terms)
        for term in women_auto_exclude:
            if term not in existing:
                exclude_terms.append(term)
    elif target_audience == "men":
        men_auto_exclude = {"women", "women's", "female", "girl", "girls", "ladies", "feminine"}
        existing = set(exclude_terms)
        for term in men_auto_exclude:
            if term not in existing:
                exclude_terms.append(term)

    # Match category to available categories
    if category:
        matched = find_matching_category(category)
        category = matched if matched else None

    # Execute search based on query type
    if query_type == "exploratory" and len(search_queries) > 1:
        # Multi-query search for exploratory queries (gifts, ideas, etc.)
        # Fetch more results per query for better diversity
        results_per_query = max(limit // len(search_queries) + 2, 5)
        results = _multi_query_search(
            queries=search_queries,
            top_k_per_query=results_per_query,
            price_max=price_max,
            category=category,
        )
    else:
        # Single query search for direct product queries
        search_text = search_queries[0] if search_queries else user_query
        fetch_limit = min(limit * 3, 30)  # Fetch 3x for better re-ranking pool
        
        results = run_embed_and_search(search_text, None, top_k=fetch_limit, price_max=price_max, category=category)
        
        # Fallback searches if no results
        if not results and (category or price_max):
            results = run_embed_and_search(search_text, None, top_k=fetch_limit, price_max=price_max, category=None)
        if not results and (category or price_max):
            results = run_embed_and_search(search_text, None, top_k=fetch_limit, price_max=None, category=category)
        if not results:
            results = run_embed_and_search(search_text, None, top_k=fetch_limit, price_max=None, category=None)
        if not results and search_text != user_query:
            results = run_embed_and_search(user_query, None, top_k=fetch_limit, price_max=None, category=None)

    # Apply negative constraints filter (category-level)
    results = _apply_negative_constraints_filter(results, negative_constraints)
    
    # Apply exclude_terms filter (title-level, e.g. remove men's products for female recipient)
    results = _apply_exclude_terms_filter(results, exclude_terms)
    
    # Re-rank results based on keyword relevance
    if primary_keywords and results:
        # First pass: try to get results with keyword matches
        reranked = _rerank_results(
            results, 
            primary_keywords, 
            boost_weight=0.6,
            require_keyword_match=True,  # Only keep results with keyword matches
        )
        
        # If we got enough results with keyword matches, use them
        if len(reranked) >= max(limit // 3, 2):
            results = reranked
        else:
            # Not enough keyword-matched results; re-rank all but still sort by relevance.
            # Keep only results that have at least SOME keyword relevance (> 0) or a high semantic score.
            all_reranked = _rerank_results(
                results, 
                primary_keywords, 
                boost_weight=0.6,
                require_keyword_match=False,
            )
            # Filter out results with zero keyword relevance AND low semantic score
            # This prevents completely unrelated products from showing up
            filtered = [
                r for r in all_reranked
                if r.get("keyword_relevance", 0) > 0 or r.get("original_score", r.get("score", 0)) >= 0.5
            ]
            results = filtered if filtered else all_reranked[:limit]
    
    # Trim to requested limit after re-ranking
    results = results[:limit]

    # Generate summary (optional)
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
        "filters_applied": {
            "price_max": price_max,
            "category": category,
            "negative_constraints": negative_constraints,
            "exclude_terms": exclude_terms,
            "target_audience": target_audience,
            "primary_keywords": primary_keywords,
            "query_type": query_type,
            "search_queries": search_queries,
        },
    }
