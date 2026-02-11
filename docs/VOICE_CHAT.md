# داکیومنت ویژگی ویس چت (Voice Chat)

این سند توضیح کامل ویژگی **ویس چت** اضافه‌شده به پروژه RAG را ارائه می‌دهد؛ از معماری کلی تا جزئیات فرانت‌اند، بک‌اند و جریان داده.

---

## فهرست

1. [خلاصه و هدف](#خلاصه-و-هدف)
2. [جریان کلی (End-to-End)](#جریان-کلی-end-to-end)
3. [معماری و اجزا](#معماری-و-اجزا)
4. [فرانت‌اند](#فرانت‌اند)
5. [بک‌اند](#بک‌اند)
6. [APIها](#apiها)
7. [جلوگیری از لوپ صوتی و قطع پخش](#جلوگیری-از-لوپ-صوتی-و-قطع-پخش)
8. [تنظیمات و وابستگی‌ها](#تنظیمات-و-وابستگی‌ها)
9. [فایل‌های کلیدی](#فایل‌های-کلیدی)

---

## خلاصه و هدف

ویس چت به کاربر اجازه می‌دهد:

- **حالت صوتی پایدار** را با یک کلیک روی دکمه میکروفون روشن کند؛ میکروفون تا زمانی که کاربر دوباره کلیک نکند روشن می‌ماند.
- **صحبت کند** و با **تشخیص خودکار پایان صحبت (VAD)** همان بخش صوتی بدون کلیک اضافه **خودکار ارسال** شود.
- **پاسخ متنی و صوتی** دریافت کند: متن در چت نمایش داده می‌شود و در صورت موفقیت TTS، پاسخ به‌صورت صوتی هم پخش می‌شود.
- در صورت انتخاب محصول(ها) در چت، **سوال درباره همان محصول(ها)** را با ویس بپرسد و پاسخ مرتبط بگیرد.

هدف، تجربهٔ مکالمهٔ صوتی روان بدون نیاز به زدن دکمه برای هر پیام است، با جلوگیری از **لوپ صوتی** (ضبط صدای اسپیکر توسط میکروفون) و امکان **قطع پخش** پاسخ ربات توسط کاربر.

---

## جریان کلی (End-to-End)

```
کاربر کلیک میکروفون → حالت صوتی روشن → VAD گوش می‌دهد
       ↓
کاربر صحبت می‌کند → VAD «شروع صحبت» → حالت «در حال ضبط»
       ↓
سکوت / پایان صحبت → VAD «پایان صحبت» → تبدیل به WAV → ارسال خودکار
       ↓
فرانت: voiceDetectIntent(voiceFile) → نمایش لودر مناسب (جستجو یا معمولی)
       ↓
فرانت: sendVoiceChat(sessionId, voiceFile, selectedProducts?)
       ↓
بک‌اند: STT (Whisper) → متن → RAG (با/بدون محصولات انتخاب‌شده) → پاسخ متنی
       ↓
بک‌اند: TTS (edge-tts) → MP3 → base64 در JSON
       ↓
فرانت: نمایش پیام کاربر (متن ترنسکریب) + پیام دستیار (متن + پخش صدا)
       ↓
وقتی پخش شروع شد → isAISpeaking = true → VAD متوقف (جلوگیری از لوپ)
وقتی پخش تمام شد (+ ۵۰۰ms) → isAISpeaking = false → VAD دوباره فعال
```

---

## معماری و اجزا

| لایه        | مسئولیت |
|------------|---------|
| **UI (MessageInput)** | دکمه میکروفون، حالت صوتی، VAD، تبدیل Float32→WAV، فراخوانی `onSendVoice` |
| **ChatPanel**         | `handleSendVoice`: `voiceDetectIntent` سپس `sendVoiceChat`، state `isAISpeaking`، قطع پخش |
| **MessageList**       | پخش `audioBase64` پاسخ، `onAudioPlayStart` / `onAudioPlayEnd` برای هماهنگی با VAD |
| **API (frontend)**    | `voiceDetectIntent(voiceFile)`, `sendVoiceChat(sessionId, voiceFile, selectedProducts?)` |
| **Backend**           | `/voice-detect-intent`, `/voice-chat`؛ STT، تشخیص قصد، RAG، TTS |

---

## فرانت‌اند

### ۱. حالت‌های UI صوتی (`VoiceUIState`)

در `MessageInput.tsx` پنج حالت برای دکمه میکروفون تعریف شده است:

| حالت | معنی |
|------|------|
| `idle` | حالت عادی؛ دکمه برای «روشن کردن حالت صوتی». |
| `listening` | حالت صوتی روشن؛ میکروفون باز، منتظر صحبت کاربر. |
| `userSpeaking` | کاربر در حال صحبت (VAD شروع صحبت را تشخیص داده). |
| `processing` | پایان صحبت تشخیص داده شده؛ در حال ارسال و دریافت پاسخ. |
| `aiSpeaking` | ربات در حال پخش پاسخ صوتی. |

این حالت‌ها برای **فیدبک بصری** (رنگ، آیکون، انیمیشن) و برای **غیرفعال/فعال کردن VAD** استفاده می‌شوند.

### ۲. VAD (تشخیص خودکار پایان صحبت)

- **کتابخانه:** `@ricky0123/vad-web` (مدل Silero در مرورگر با ONNX).
- **مسیر assets:**  
  - Worklet/ONNX از CDN: `https://cdn.jsdelivr.net/npm/@ricky0123/vad-web@0.0.27/dist/`  
  - WASM از same-origin: `/onnxruntime-web/` (کپی در `postinstall` از `node_modules/onnxruntime-web/dist` به `public/onnxruntime-web`).
- **پارامترها (نمونه):**
  - `minSpeechMs: 300`
  - `redemptionMs: 1200`
  - `positiveSpeechThreshold` / `negativeSpeechThreshold: 0.2`
- **حداقل طول برای ارسال:** اگر طول `audio` در `onSpeechEnd` کمتر از `MIN_VOICE_SAMPLES` (حدود ۰٫۱ ثانیه در ۱۶kHz) باشد، ارسال انجام نمی‌شود.
- **خروجی VAD:** `Float32Array` 16kHz mono → با تابع `float32ToWavFile` در `audioUtils.ts` به فایل WAV تبدیل و به `onSendVoice(file, attachedProducts?)` داده می‌شود.

### ۳. تبدیل صدا به فایل (WAV)

- **فایل:** `frontend/lib/audioUtils.ts`
- **تابع:** `float32ToWavFile(samples, sampleRate = 16000)`: Float32 (۱۶kHz، مونو) را به WAV 16-bit PCM تبدیل و به صورت `File` برمی‌گرداند تا برای API ارسال شود.

### ۴. محصولات انتخاب‌شده (Attached Products)

- کاربر می‌تواند روی کارت محصول در چت کلیک کند و آن را «انتخاب» کند.
- در **حالت صوتی**، وقتی VAD یک بخش را ارسال می‌کند، اگر محصول(ها) انتخاب شده باشد، همان لیست به عنوان `attachedProducts` به `onSendVoice(file, productsToSend)` و سپس به `sendVoiceChat(..., selectedProducts)` فرستاده می‌شود.
- بک‌اند این لیست را در متن مؤثر (context محصولات) قبل از سوال کاربر قرار می‌دهد تا پاسخ درباره همان محصول(ها) باشد.

### ۵. نمایش پاسخ صوتی و کنترل پخش

- در `MessageList.tsx` برای **آخرین پیام دستیار** در همان session، اگر `audioBase64` وجود داشته باشد، یک المان `<audio>` با `autoPlay` و با `onPlay` / `onEnded` رندر می‌شود.
- `onPlay` → `onAudioPlayStart()` (در ChatPanel: `setAISpeaking(true)`).
- `onEnded` → `onAudioPlayEnd()` (در ChatPanel: بعد از **۵۰۰ms** تأخیر `setAISpeaking(false)`).
- یک `voiceAudioRef` از ChatPanel به MessageList پاس داده می‌شود تا در صورت نیاز (مثلاً قطع توسط کاربر) بتوان `audio.pause()` فراخوانی کرد.

---

## بک‌اند

### ۱. مسیرهای موقت

- **پوشه صوتی:** `VOICE_TEMP_DIR` در `config.py` (مثلاً `backend/temp/voice`).
- فایل آپلود شده در یک فایل موقت ذخیره، پس از STT حذف می‌شود. در startup اپلیکیشن این پوشه خالی می‌شود.

### ۲. Speech-to-Text (STT)

- **سرویس:** `backend/app/services/stt.py`
- **مدل:** `faster-whisper` (سایز از `WHISPER_MODEL_SIZE`، پیش‌فرض `small`)، Singleton، int8 برای GPU/CPU.
- **ورودی:** مسیر فایل صوتی. ترجیحاً فایل با ffmpeg به **16kHz mono WAV** تبدیل می‌شود تا از خطاهای فرمت (مثل Opus) جلوگیری شود.
- **خروجی:** متن ترنسکریب‌شده (یک رشته).
- مدل Whisper در startup بارگذاری می‌شود تا اولین درخواست ویس timeout نخورد.

### ۳. Text-to-Speech (TTS)

- **سرویس:** `backend/app/services/tts.py`
- **موتور:** `edge-tts` (آنلاین، مایکروسافت).
- **زبان:** با `langdetect` از روی متن تشخیص داده می‌شود؛ برای زبان‌های مشخص (مثل `fa`, `tr`) صدا از config خوانده می‌شود، وگرنه از `TTS_VOICE_MAP` (۵۰+ زبان).
- **خروجی:** بایت‌های MP3؛ در API به صورت base64 در JSON برگردانده می‌شود. در صورت خطا، پاسخ بدون `audio_base64` برمی‌گردد (degradation نرم).

### ۴. تشخیص قصد (Intent)

- **سرویس:** `detect_intent_with_llm` در `backend/app/services/rag.py`.
- برای **ویس** ابتدا فایل صوتی ترنسکریب می‌شود، سپس همین تابع روی متن فراخوانی می‌شود.
- خروجی شامل `needs_qdrant_search` و `intent_type` است و در فرانت برای انتخاب نوع لودر (جستجو در Qdrant یا معمولی) استفاده می‌شود.

---

## APIها

### ۱. `POST /api/voice-detect-intent`

- **ورودی:** `voice`: فایل صوتی (مثلاً WAV/WebM).
- **خروجی (JSON):**
  - `transcribed_text`: متن ترنسکریب‌شده
  - `needs_qdrant_search`: boolean
  - `intent_type`: رشته (مثل product_search, faq, chitchat, …)
  - `confidence`: عدد
- **کاربرد در فرانت:** قبل از `sendVoiceChat` فراخوانی می‌شود تا هم متن برای نمایش/fallback داشته باشیم و هم نوع لودر را تنظیم کنیم.

### ۲. `POST /api/voice-chat`

- **ورودی (Form):**
  - `session_id`: عدد
  - `voice`: فایل صوتی
  - `selected_products`: (اختیاری) آرایه JSON از محصولات انتخاب‌شده برای context
- **پردازش:**  
  STT → ساخت `effective_message` (در صورت وجود محصولات، context محصول + متن) → RAG/چت → TTS.
- **خروجی (JSON):**
  - `message`: پاسخ متنی
  - `products`: لیست محصولات در پاسخ
  - `transcribed_text`: متن ترنسکریب‌شده
  - `audio_base64`: (اختیاری) MP3 پاسخ به صورت base64
- در صورت خطای TTS، فقط `audio_base64` حذف می‌شود و بقیه فیلدها برگردانده می‌شوند.

---

## جلوگیری از لوپ صوتی و قطع پخش

### لوپ صوتی (Feedback Loop)

- **مشکل:** پخش صدای ربات از اسپیکر → ضبط همان صدا توسط میکروفون → ارسال دوباره به سرور → پاسخ تکراری و لوپ.
- **راه‌حل:**
  - وقتی پخش پاسخ ربات **شروع** می‌شود (`onPlay`): `isAISpeaking = true` → در `MessageInput` VAD **متوقف (pause)** می‌شود.
  - وقتی پخش **تمام** می‌شود (`onEnded`): بعد از **۵۰۰ms** تأخیر `isAISpeaking = false` و VAD دوباره **resume** می‌شود تا اکوی محیط از بین برود.

### قطع پخش (Interruption)

- اگر کاربر در حین پخش پاسخ، **دکمه میکروفون را بزند** (خاموش کردن حالت صوتی)، تابع `onStopAIPlayback` فراخوانی می‌شود که:
  - تایمر ۵۰۰ms را لغو می‌کند،
  - `isAISpeaking = false` می‌کند،
  - و `voiceAudioRef.current?.pause()` را صدا می‌زند تا پخش قطع شود.

---

## تنظیمات و وابستگی‌ها

### فرانت‌اند

- **پکیج:** `@ricky0123/vad-web@^0.0.27`
- **وابستگی VAD:** `onnxruntime-web`؛ فایل‌های WASM/.mjs از `node_modules/onnxruntime-web/dist` در `postinstall` به `public/onnxruntime-web` کپی می‌شوند (اسکریپت `frontend/scripts/copy-onnx-wasm.js`).

### بک‌اند

- **متغیرهای محیط (نمونه):**
  - `WHISPER_MODEL_SIZE`: سایز مدل Whisper (مثلاً tiny, base, small, medium).
  - `TTS_VOICE_FA`, `TTS_VOICE_EN`, `TTS_VOICE_TR`, `TTS_VOICE`: صداهای edge-tts برای زبان‌های مشخص.
- **وابستگی‌ها:** `faster-whisper`, `edge-tts`, `langdetect`, و برای تبدیل صدا `ffmpeg` (در PATH یا `FFMPEG_PATH`).

---

## فایل‌های کلیدی

| فایل | نقش |
|------|-----|
| `frontend/components/chat/MessageInput.tsx` | حالت صوتی، VAD، دکمه میکروفون، حالت‌های UI، pause/resume با `isAISpeaking`. |
| `frontend/components/chat/ChatPanel.tsx` | `handleSendVoice`، `voiceDetectIntent` + `sendVoiceChat`، state `isAISpeaking`، `handleAudioPlayStart/End`، `stopAIPlayback`. |
| `frontend/components/chat/MessageList.tsx` | پخش `audioBase64`، ref صدا، `onAudioPlayStart` / `onAudioPlayEnd`. |
| `frontend/lib/api.ts` | `voiceDetectIntent(voiceFile)`, `sendVoiceChat(sessionId, voiceFile, selectedProducts?)`. |
| `frontend/lib/audioUtils.ts` | `float32ToWavFile` برای تبدیل خروجی VAD به WAV. |
| `backend/app/api/chat.py` | اندپوینت‌های `/voice-detect-intent` و `/voice-chat`. |
| `backend/app/services/stt.py` | ترنسکریب با faster-whisper، تبدیل به WAV با ffmpeg. |
| `backend/app/services/tts.py` | سنتز صدا با edge-tts، تشخیص زبان، خروجی MP3. |
| `backend/app/services/rag.py` | `detect_intent_with_llm` و جریان RAG/چت. |
| `backend/app/config.py` | `VOICE_TEMP_DIR`, `WHISPER_MODEL_SIZE`, صداهای TTS. |

---

این داکیومنت با وضعیت فعلی کد پروژه هماهنگ است و می‌توان آن را برای onboarding یا توسعه بعدی ویس چت استفاده کرد.
