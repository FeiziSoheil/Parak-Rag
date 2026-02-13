# داکیومنت ویژگی خواندن با صدای بلند (Read Aloud)

این سند ویژگی **Read Aloud** (خواندن با صدای بلند) را توضیح می‌دهد: کاربر می‌تواند هر پاسخ متنی دستیار را با یک کلیک به صوت تبدیل کند. زبان متن ابتدا با **LLM** تشخیص داده می‌شود و سپس با **TTS** متناسب همان زبان خوانده می‌شود.

---

## فهرست

1. [خلاصه و هدف](#خلاصه-و-هدف)
2. [جریان کلی (End-to-End)](#جریان-کلی-end-to-end)
3. [معماری و اجزا](#معماری-و-اجزا)
4. [بک‌اند](#بک‌اند)
5. [فرانت‌اند](#فرانت‌اند)
6. [API](#api)
7. [فایل‌های کلیدی](#فایل‌های-کلیدی)

---

## خلاصه و هدف

Read Aloud به کاربر اجازه می‌دهد:

- روی هر **پاسخ متنی دستیار** دکمهٔ «خواندن با صدای بلند» (آیکون بلندگو) را بزند.
- **زبان متن** به‌صورت خودکار با **LLM** تشخیص داده شود (بدون وابستگی به کلمات ثابت یا کتابخانهٔ langdetect در این مرحله).
- با **TTS** (edge-tts) و **صدای مناسب همان زبان**، متن به صورت صوتی پخش شود.
- در حین پخش، حالت «AI در حال صحبت» فعال باشد تا در صورت استفاده همزمان از ویس چت، **VAD متوقف** شود و از لوپ صوتی جلوگیری شود.

هدف، دسترسی آسان به شنیدن پاسخ‌های متنی با تلفظ و لهجهٔ درست بر اساس زبان تشخیص‌داده‌شده است.

---

## جریان کلی (End-to-End)

```
کاربر روی «Read aloud» کنار یک پیام دستیار کلیک می‌کند
       ↓
فرانت: readAloud(messageContent) → POST /api/read-aloud با text
       ↓
بک‌اند: _strip_markdown_for_tts(text) → حذف **، ##، لیست‌ها و ...
       ↓
بک‌اند: detect_language_with_llm(plain) → کد زبان ISO 639-1 (مثلاً fa، en، ar)
       ↓
بک‌اند: text_to_speech_to_bytes(plain, lang=detected_lang) → MP3
       ↓
بک‌اند: برگرداندن { audio_base64, detected_lang }
       ↓
فرانت: ست کردن src المان صوتی readAloudAudioRef و play()
       ↓
onAudioPlayStart() → isAISpeaking = true → VAD در ویس چت متوقف
       ↓
پخش تمام شد → onAudioPlayEnd() → بعد از ۵۰۰ms → isAISpeaking = false
```

---

## معماری و اجزا

| لایه | مسئولیت |
|------|---------|
| **MessageList** | دکمهٔ Read aloud کنار هر پیام دستیار، حالت loading، فراخوانی `onReadAloud(content)` |
| **ChatPanel** | `handleReadAloud`: فراخوانی `readAloud(text)`، پخش از طریق `readAloudAudioRef`، هماهنگی `onAudioPlayStart`/`onAudioPlayEnd` و `stopAIPlayback` |
| **API (frontend)** | `readAloud(text)` → `POST /api/read-aloud` |
| **Backend** | `/read-aloud`: حذف مارک‌داون، تشخیص زبان با LLM، TTS با زبان مشخص، برگرداندن base64 |

---

## بک‌اند

### ۱. حذف مارک‌داون برای TTS

تابع **`_strip_markdown_for_tts(text)`** در `chat.py` مارک‌داون متداول را از متن حذف می‌کند تا TTS عبارت‌هایی مثل «ستاره ستاره» یا «هش» را نخواند:

- **bold**: `**...**`, `__...__`
- **italic**: `*...*`, `_..._`
- **عنوان**: `## ...`
- **لیست**: `-`, `*`, `•`, `1.`
- فشرده‌سازی خطوط خالی متوالی

خروجی متن ساده برای سنتز صدا است.

### ۲. تشخیص زبان با LLM

تابع **`detect_language_with_llm(text)`** در `app/services/rag.py`:

- از همان **OpenRouter / LangChain** (مدل `OPENROUTER_MODEL`) استفاده می‌کند.
- پرامپت: «زبان این متن را مشخص کن؛ فقط یک کد ISO 639-1 برگردان (مثلاً en, fa, ar, zh-cn).»
- خروجی LLM پردازش می‌شود (حذف فاصله، نقطه، خط جدید؛ استخراج اولین توکن).
- برای چینی: `zh-cn` یا `zh-tw`؛ در غیر این صورت کد دوحرفی (مثل `fa`, `en`).
- در صورت خطا یا نبود API key، مقدار پیش‌فرض **`en`** برمی‌گردد.

### ۳. TTS با زبان تحمیل‌شده

در `app/services/tts.py`:

- **`_get_voice_for_language(text, voice_override, lang_override)`**: اگر `lang_override` داده شده باشد، از آن برای انتخاب صدا استفاده می‌شود و دیگر `_detect_language(text)` (langdetect) صدا زده نمی‌شود.
- **`text_to_speech_to_bytes(text, voice=None, lang=None)`**: پارامتر **`lang`** اضافه شده؛ در read-aloud با `lang=detected_lang` فراخوانی می‌شود تا صدا مطابق زبان تشخیص‌داده‌شده توسط LLM انتخاب شود.

صدای edge-tts از **TTS_VOICE_MAP** (بیش از ۵۰ زبان) و در صورت تنظیم از **TTS_VOICE_FA**, **TTS_VOICE_TR** و غیره انتخاب می‌شود.

### ۴. اندپوینت Read Aloud

- **مسیر:** `POST /api/read-aloud`
- **ورودی (Form):** `text` — متن پیام دستیار (می‌تواند مارک‌داون داشته باشد).
- **پردازش:**
  1. حذف مارک‌داون با `_strip_markdown_for_tts`.
  2. رد کردن متن خالی یا خیلی کوتاه (کمتر از ۲ کاراکتر) → **400**.
  3. تشخیص زبان با `detect_language_with_llm(plain)` (در executor).
  4. سنتز صدا با `text_to_speech_to_bytes(plain, lang=detected_lang)`.
  5. در صورت شکست TTS → **502**.
- **خروجی (JSON):**  
  `{ "audio_base64": "...", "detected_lang": "fa" }`  
  (MP3 به صورت base64 و کد زبان تشخیص‌داده‌شده.)

---

## فرانت‌اند

### ۱. API

در `lib/api.ts`:

- **`readAloud(text: string): Promise<ReadAloudResult>`**  
  - `ReadAloudResult = { audio_base64: string; detected_lang?: string }`
- درخواست: `POST /api/read-aloud` با `FormData` شامل فیلد `text`.
- در صورت خطا (۴۰۰، ۵۰۲، …) خطا پرتاب می‌شود.

### ۲. ChatPanel

- **`readAloudAudioRef`**: رفر به المان `<audio>` پنهان که فقط برای پخش Read aloud استفاده می‌شود.
- **`<audio ref={readAloudAudioRef} … onPlay={handleAudioPlayStart} onEnded={handleAudioPlayEnd} />`**: با پخش همان المان، `isAISpeaking` روشن/خاموش می‌شود تا VAD ویس چت در حین پخش متوقف باشد.
- **`handleReadAloud(text)`**:  
  - فراخوانی `readAloud(text)`، سپس ست کردن `src` با `data:audio/mpeg;base64,${audio_base64}` و `play()` روی `readAloudAudioRef.current`.
- **`stopAIPlayback`**: علاوه بر `voiceAudioRef`، **`readAloudAudioRef.current?.pause()`** هم فراخوانی می‌شود تا پخش Read aloud هم با دکمهٔ قطع ویس متوقف شود.

### ۳. MessageList

- برای هر پیام **دستیار** که `content` دارد، کنار دکمهٔ Copy یک دکمهٔ **Read aloud** (آیکون `Volume2`) نمایش داده می‌شود.
- **Prop:** `onReadAloud?: (text: string) => Promise<void>`؛ در صورت نبودن، دکمه نمایش داده نمی‌شود.
- با کلیک: **`handleReadAloud(m.content, m.id)`** صدا زده می‌شود؛ تا پایان درخواست، **`readAloudLoadingId === m.id`** و دکمه در حالت loading (اسپینر) و غیرفعال است.

---

## API

### `POST /api/read-aloud`

| مورد | مقدار |
|------|--------|
| **احراز هویت** | لازم (Bearer token) |
| **ورودی** | `application/x-www-form-urlencoded` یا `multipart/form-data`: فیلد **`text`** (متن برای خواندن) |
| **خروجی موفق (200)** | `{ "audio_base64": "<base64 MP3>", "detected_lang": "<ISO 639-1>" }` |
| **۴۰۰** | متن خالی یا خیلی کوتاه |
| **۵۰۲** | خطا در TTS (مثلاً edge-tts در دسترس نبود) |

---

## فایل‌های کلیدی

| فایل | نقش |
|------|-----|
| `backend/app/api/chat.py` | `_strip_markdown_for_tts`، اندپوینت `POST /read-aloud` |
| `backend/app/services/rag.py` | `detect_language_with_llm(text)` — تشخیص زبان با LLM |
| `backend/app/services/tts.py` | `_get_voice_for_language(..., lang_override)`، `text_to_speech_to_bytes(..., lang=...)` |
| `frontend/lib/api.ts` | `readAloud(text)`، نوع `ReadAloudResult` |
| `frontend/components/chat/ChatPanel.tsx` | `readAloudAudioRef`، `handleReadAloud`، المان صوتی و اتصال به `onAudioPlayStart`/`onAudioPlayEnd` و `stopAIPlayback` |
| `frontend/components/chat/MessageList.tsx` | دکمهٔ Read aloud، `readAloudLoadingId`، `handleReadAloud`، prop `onReadAloud` |

---

## وابستگی‌ها

- **بک‌اند:** همان مدل LLM و کلید OpenRouter (`OPENROUTER_API_KEY`, `OPENROUTER_MODEL`)، edge-tts، و در TTS در صورت عدم ارسال `lang` کتابخانهٔ langdetect (برای سایر جریان‌ها مثل voice-chat).
- **فرانت‌اند:** وابستگی جدیدی اضافه نشده؛ از همان المان صوتی و state مربوط به ویس چت (`isAISpeaking`) استفاده می‌شود.

این داکیومنت با وضعیت فعلی کد هماهنگ است و برای onboarding یا توسعهٔ بعدی بخش Read Aloud قابل استفاده است.
