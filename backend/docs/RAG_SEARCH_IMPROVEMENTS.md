# مستند تغییرات سیستم جستجو و RAG (پَرَک)

**تاریخ:** ۲۰۲۶-۰۲-۱۲  
**فایل‌های اصلی:** `app/services/rag.py`, `app/api/chat.py`

---

## فهرست

1. [خلاصه تغییرات](#۱-خلاصه-تغییرات)
2. [معماری و فلوی جستجو](#۲-معماری-و-فلوی-جستجو)
3. [پرامپت‌های سیستم](#۳-پرامپت‌های-سیستم)
4. [توابع جدید و بهبود یافته](#۴-توابع-جدید-و-بهبود-یافته)
5. [پارامترها و پیکربندی](#۵-پارامترها-و-پیکربندی)
6. [استفاده در چت و ویس چت](#۶-استفاده-در-چت-و-ویس-چت)

---

## ۱. خلاصه تغییرات

### اهداف بهبود

- **جستجوی مستقیم (مثل «قاب گوشی»):** محصول مرتبط (مثلاً Armor Case) در رتبه اول نمایش داده شود، نه در رتبه چهارم.
- **جستجوی اکتشافی (مثل «کادو برای مادر»):** محصولات واقعاً مرتبط با هدیه (عطر، جواهر، ساعت، و غیره) نمایش داده شوند، نه محصولات نامرتبط.
- **راه‌حل کلی:** بدون لیست ثابت کلمات کلیدی؛ استفاده از LLM برای فهم intent و استخراج پارامترهای جستجو به‌صورت هوشمند.

### تغییرات اصلی

| بخش | قبل | بعد |
|-----|-----|-----|
| نوع جستجو | یک کوئری واحد برای همه | تفکیک **direct** (یک کوئری) و **exploratory** (چند کوئری موازی) |
| جستجو | فقط یک بار embed + Qdrant | برای exploratory: چند جستجوی موازی با کوئری‌های مختلف |
| رتب‌بندی | فقط امتیاز شباهت (CLIP) | ترکیب امتیاز semantic + **keyword relevance** و re-ranking |
| تطابق با محصول | فقط embedding | بررسی تطابق کلمات کلیدی در **subject**, **category_name**, **context_text** |

---

## ۲. معماری و فلوی جستجو

### فلوی کلی `enhanced_search_with_llm`

```
ورودی: user_query, limit, price_max?, category?, last_shown_products?
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ ۱. دریافت لیست دسته‌بندی‌های موجود از Qdrant               │
│    (analyze_collection_data)                                 │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ ۲. پرامپت LLM: تحلیل کوئری و خروجی JSON                    │
│    → query_type, search_queries, primary_keywords,          │
│      price_max?, category?, negative_constraints             │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ ۳. اجرای جستجو                                              │
│    • exploratory + چند search_query:                        │
│      _multi_query_search(queries, top_k_per_query, ...)     │
│    • direct: run_embed_and_search(اولین کوئری, top_k=3×limit)│
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ ۴. فیلتر محدودیت‌های منفی (negative_constraints)             │
│    _apply_negative_constraints_filter                        │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ ۵. Re-ranking با _rerank_results                            │
│    • اگر primary_keywords داریم:                            │
│      - اول: require_keyword_match=True                      │
│      - اگر نتیجه‌های با keyword match کمتر از limit/2 بود:   │
│        require_keyword_match=False و فقط re-rank            │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ ۶. برش تا limit نتیجه، اختیاری: تولید summary با LLM        │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
خروجی: { query, results, summary?, filters_applied }
```

### جایی که ویس چت استفاده می‌کند

هم **چت متنی** (`POST /chat`) و هم **ویس چت** (`POST /voice-chat`) از تابع مشترک `_run_chat_response` در `app/api/chat.py` استفاده می‌کنند. در ویس چت فقط قبل از آن صدا با STT به متن تبدیل می‌شود؛ بعد همان مسیر جستجو و RAG اجرا می‌شود. بنابراین **همه تغییرات جستجو به‌طور خودکار برای ویس چت هم اعمال شده‌اند.**

---

## ۳. پرامپت‌های سیستم

### ۳.۱. پرامپت اصلی دستیار (RAG پاسخ‌گویی)

**متغیر:** `SYSTEM_PROMPT` در `rag.py`

**کاربرد:** در `run_rag_response`, `_invoke_chain_sync`, `_run_stream_into_queue` — برای تولید پاسخ متنی بر اساس context (فروشگاه، FAQ، محصولات).

```
You are PARAK (پَرَک), an intelligent assistant (دستیار هوشمند). You help users with product search, store information, and FAQ; be friendly, accurate, and concise.

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
- If the user searched by image and we found similar products: reply with a short message presenting the results (e.g. "Here are similar products I found based on your image" or "I found these similar products for you."). Do NOT ask the user for more details or keywords.
```

**اضافه شدن در زمان اجرا:**  
`"\n\n**Product context:**\n{context}"`  
و در صورت جستجو با تصویر و وجود نتیجه: یک یادداشت کوتاه برای ارائه نتایج مشابه بر اساس تصویر.

---

### ۳.۲. پرامپت تشخیص قصد (Intent Detection)

**کاربرد:** `detect_intent_with_llm(message)` — تشخیص نیاز به جستجو در Qdrant (محصول / فروشگاه / FAQ) یا فقط چت/سلام.

**قالب پرامپت:**

```
Analyze this user message and determine the intent. Respond with ONLY a JSON object.

User message: "{message}"

Determine:
1. Does this message require searching a product database/catalog? (e.g. looking for products, asking about items, prices, recommendations)
2. Does this message require searching store information? (e.g. store hours, location, contact)
3. Does this message require searching FAQ? (e.g. return policy, shipping, payment methods)
4. Is this just a greeting or chitchat? (e.g. hello, how are you, what's your name)

Respond with this exact JSON schema:
{
  "needs_qdrant_search": true/false,
  "intent_type": "product_search" | "store_info" | "faq" | "chitchat" | "greeting" | "unknown",
  "confidence": 0.0-1.0
}

Rules:
- needs_qdrant_search = true if intent_type is "product_search", "store_info", or "faq"
- needs_qdrant_search = false if intent_type is "chitchat" or "greeting"
- For ambiguous messages, lean towards needs_qdrant_search = true
- Works for ANY language (English, Persian, French, Chinese, etc.)
```

**خروجی:** `{ "needs_qdrant_search": bool, "intent_type": str, "confidence": float }`

---

### ۳.۳. پرامپت تحلیل کوئری جستجو (Search Query Analysis)

**کاربرد:** داخل `enhanced_search_with_llm` — تعیین نوع جستجو، کوئری‌های جستجو، کلمات کلیدی اصلی و فیلترها.

**متغیرهای تزریق شده در پرامپت:**  
`categories_context`, `last_products_block`, `user_query`

**متن کامل پرامپت:**

```
Analyze this product search query and respond with a single JSON object.

**Schema (all fields required; use null or empty array where not applicable):**
- query_type: string ("direct" for specific product search, "exploratory" for gift/idea/recommendation queries)
- search_queries: array of strings (English search queries to execute. For direct queries, use 1-2 queries. For exploratory queries like gifts, use 3-5 specific product type queries like ["perfume fragrance", "jewelry necklace bracelet", "watch smartwatch", "skincare beauty"])
- primary_keywords: array of strings (keywords that should appear in relevant product titles, ordered by importance)
- price_max: number | null (only if user explicitly mentions price)
- category: string | null (one of the available categories, or null)
- negative_constraints: array of strings (things user does NOT want)

Available categories: {categories_context}
{last_products_block}

**Examples:**

Example 1 – Direct product query:
Query: "قاب گوشی"
Response: {"query_type": "direct", "search_queries": ["phone case cover protective"], "primary_keywords": ["case", "cover", "phone case", "protective"], "price_max": null, "category": null, "negative_constraints": []}

Example 2 – Direct product query:
Query: "هدفون بلوتوث"
Response: {"query_type": "direct", "search_queries": ["bluetooth headphone wireless earphone"], "primary_keywords": ["headphone", "earphone", "headset", "earbuds", "bluetooth", "wireless"], "price_max": null, "category": null, "negative_constraints": []}

Example 3 – Gift for mother (exploratory):
Query: "کادو برای مادر" or "هدیه روز مادر"
Response: {"query_type": "exploratory", "search_queries": ["perfume fragrance women scent", "jewelry necklace bracelet ring", "skincare beauty cream serum", "watch women elegant", "scarf shawl fashion"], "primary_keywords": ["perfume", "fragrance", "jewelry", "necklace", "skincare", "beauty", "watch", "scarf", "gift", "women"], "price_max": null, "category": null, "negative_constraints": []}

Example 4 – Gift for spouse birthday:
Query: "کادو تولد همسر"
Response: {"query_type": "exploratory", "search_queries": ["perfume cologne fragrance", "jewelry ring necklace", "watch smartwatch elegant", "wallet leather accessories"], "primary_keywords": ["perfume", "jewelry", "watch", "wallet", "gift", "romantic"], "price_max": null, "category": null, "negative_constraints": []}

Example 5 – Gift for child (no toys):
Query: "کادو برای بچه ولی اسباب بازی نباشه"
Response: {"query_type": "exploratory", "search_queries": ["children books educational", "kids clothes fashion", "school supplies stationery", "children shoes sneakers"], "primary_keywords": ["kids", "children", "educational", "books", "clothes", "school"], "price_max": null, "category": null, "negative_constraints": ["toys", "toy", "game"]}

Example 6 – Teacher's day gift:
Query: "هدیه روز معلم"
Response: {"query_type": "exploratory", "search_queries": ["pen set elegant writing", "notebook journal planner", "desk organizer office", "mug cup gift"], "primary_keywords": ["pen", "notebook", "planner", "desk", "office", "gift", "elegant"], "price_max": null, "category": null, "negative_constraints": []}

Query: "{user_query}"

Respond with JSON only, no other text.
```

**خروجی مورد انتظار:**  
یک آبجکت JSON با فیلدهای `query_type`, `search_queries`, `primary_keywords`, `price_max`, `category`, `negative_constraints`.

---

### ۳.۴. پرامپت خلاصه نتایج جستجو (Search Summary)

**کاربرد:** بعد از به‌دست آوردن نتایج در `enhanced_search_with_llm` — تولید یک خلاصه متنی کوتاه برای نتایج (اختیاری).

**قالب:**

```
Based on the search query "{user_query}", I found these products:
{lines}

Provide a brief, helpful summary (2-3 sentences) about these search results.
```

`lines`: لیست متنی چند خطی از عنوان، قیمت و دسته‌بندی حداکثر ۵ محصول اول.

---

### ۳.۵. پرامپت‌های خوش‌آمدگویی (Welcome)

**کاربرد:** `generate_welcome(welcome_type, username)`.

- **dashboard:**  
  `"The user named {username or "Guest"} just entered the dashboard. Write a short, friendly welcome message in English (one or two sentences). Plain text only, no greeting prefix or signature."`

- **new_chat:**  
  `"The user just opened a new chat. Write a short welcome in English and suggest two or three example questions they could ask (e.g. product search) as short sentences. Plain flowing text only, no numbers or bullets."`

---

## ۴. توابع جدید و بهبود یافته

### ۴.۱. `_compute_keyword_relevance(payload, keywords) -> tuple[float, bool]`

- **ورودی:**  
  - `payload`: دیکشنری یک نقطه Qdrant (شامل `subject`, `category_name`, `context_text`).  
  - `keywords`: لیست کلمات کلیدی به‌ترتیب اهمیت.
- **خروجی:**  
  - امتیاز relevance (عددی ≥ ۰، ممکن است بزرگ‌تر از ۱).  
  - `has_primary_match`: آیا حداقل یکی از سه کلمه اول در `subject` یا `category` پیدا شده است.
- **منطق:**  
  - وزن هارمونیک برای کلمات: `weight = 1/(i+1)`.  
  - تطابق در **subject**: امتیاز بیشتر + تشخیص primary match برای ۳ کلمه اول.  
  - تطابق در **category**: امتیاز کمتر، همین‌طور می‌تواند primary match باشد.  
  - تطابق در **context_text**: امتیاز ضعیف‌تر.

---

### ۴.۲. `_rerank_results(results, primary_keywords, boost_weight=0.5, require_keyword_match=False)`

- **ورودی:**  
  - `results`: خروجی جستجو با `payload` و `score`.  
  - `primary_keywords`: همان لیست کلمات کلیدی.  
  - `boost_weight`: ضریب اثر relevance روی امتیاز نهایی.  
  - `require_keyword_match`: اگر True باشد، فقط نتیجه‌هایی که حداقل یک primary match دارند نگه داشته می‌شوند.
- **خروجی:** لیست همان نتایج با فیلدهای اضافه `original_score`, `keyword_relevance`, `has_primary_match` و `score` به‌روز شده، مرتب‌شده بر اساس `score` نزولی.
- **فرمول امتیاز:**  
  `final_score = original_score * (1 + keyword_relevance * boost_weight)`  
  و در صورت `has_primary_match`: `final_score *= 1.2`.

---

### ۴.۳. `_multi_query_search(queries, top_k_per_query=10, price_max=None, category=None)`

- **ورودی:**  
  - `queries`: لیست رشته‌های کوئری (به انگلیسی).  
  - `top_k_per_query`: تعداد نتیجه برای هر کوئری.  
  - `price_max`, `category`: فیلتر اختیاری.
- **خروجی:** ادغام نتایج همه کوئری‌ها با حذف تکراری بر اساس `product_id`.
- **کاربرد:** برای `query_type == "exploratory"` و زمانی که `search_queries` بیش از یکی است.

---

### ۴.۴. `enhanced_search_with_llm(...)`

- **ورودی:**  
  `user_query`, `limit=10`, `price_max=None`, `category=None`, `last_shown_products=None`.
- **خروجی:**  
  `{ "query", "results", "summary", "filters_applied" }`.  
  در `filters_applied`: `price_max`, `category`, `negative_constraints`, `primary_keywords`, `query_type`, `search_queries`.
- **رفتار:**  
  - بدون `OPENROUTER_API_KEY`: فقط `run_embed_and_search` با همان فیلترها.  
  - با API key: طبق فلوی بخش ۲ (تحلیل کوئری → جستجو → فیلتر منفی → re-rank → برش و اختیاری summary).

---

## ۵. پارامترها و پیکربندی

| پارامتر / ثابت | محل | توضیح |
|----------------|-----|--------|
| `RAG_TOP_K` | config | تعداد پیش‌فرض نتایج جستجو (مثلاً ۵). |
| `RAG_SCORE_THRESHOLD` | config | آستانه امتیاز Qdrant (مثلاً ۰.۷). |
| `MIN_SCORE_TO_DISPLAY` | config | حداقل امتیاز برای نمایش محصول به کاربر (مثلاً ۰.۳۵). |
| `limit` | ورودی جستجو | تعداد نهایی نتایج برگشتی؛ در جستجوی مستقیم معمولاً `fetch_limit = min(limit*3, 30)`. |
| `results_per_query` | exploratory | `max(limit // len(search_queries) + 2, 5)`. |
| `boost_weight` | _rerank_results | ۰.۵. |
| `require_keyword_match` | _rerank_results | اول True؛ اگر تعداد نتایج با keyword match کمتر از `limit//2` بود، یک بار دیگر با False فراخوانی می‌شود. |

---

## ۶. استفاده در چت و ویس چت

- **چت متنی (`POST /chat`):**  
  متن کاربر + اختیاری تصویر → `_run_chat_response` → در صورت نیاز جستجو، `enhanced_search_with_llm` با `user_text` و `last_shown_products` فراخوانی می‌شود.

- **ویس چت (`POST /voice-chat`):**  
  فایل صوتی → STT (`transcribe_audio`) → متن transcribe شده (و در صورت ارسال، `selected_products` به‌صورت context به متن اضافه می‌شود) → همان `_run_chat_response` با `effective_message` و بدون تصویر.  
  بنابراین همان مسیر جستجو و RAG (از جمله تمام پرامپت‌ها و re-ranking) برای ویس چت هم یکسان است.

- **تشخیص قصد:**  
  در هر دو مسیر، قبل از جستجو می‌توان از `detect_intent_with_llm` (یا در API از endpointهای `detect-intent` / `voice-detect-intent`) استفاده کرد تا مشخص شود آیا اصلاً به Qdrant نیاز است یا نه.

---

*پایان مستند.*
