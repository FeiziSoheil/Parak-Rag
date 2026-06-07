"""Text-to-Speech using edge-tts (online). Output to BytesIO for Base64 in JSON.
Supports 50+ languages via language detection and locale-specific neural voices."""
import io
import logging
from typing import Optional

import edge_tts

from app.config import TTS_VOICE_EN, TTS_VOICE_FA, TTS_VOICE_TR

logger = logging.getLogger(__name__)

# Map langdetect ISO 639-1 code -> edge-tts neural voice (one per language, 50+).
# Fallback for unmapped languages: TTS_VOICE_EN.
TTS_VOICE_MAP = {
    "af": "af-ZA-AdriNeural",
    "am": "am-ET-MekdesNeural",
    "ar": "ar-EG-SalmaNeural",
    "az": "az-AZ-BanuNeural",
    "bg": "bg-BG-KalinaNeural",
    "bn": "bn-IN-TanishaaNeural",
    "bs": "bs-BA-VesnaNeural",
    "ca": "ca-ES-JoanaNeural",
    "cs": "cs-CZ-VlastaNeural",
    "cy": "cy-GB-NiaNeural",
    "da": "da-DK-ChristelNeural",
    "de": "de-DE-KatjaNeural",
    "el": "el-GR-AthinaNeural",
    "en": "en-US-JennyNeural",
    "es": "es-ES-ElviraNeural",
    "et": "et-EE-AnuNeural",
    "eu": "eu-ES-AinhoaNeural",
    "fa": "fa-IR-DilaraNeural",
    "fi": "fi-FI-NooraNeural",
    "fil": "fil-PH-LeilaNeural",
    "fr": "fr-FR-DeniseNeural",
    "ga": "ga-IE-OrlaNeural",
    "gl": "gl-ES-SabelaNeural",
    "gu": "gu-IN-DhwaniNeural",
    "he": "he-IL-HilaNeural",
    "hi": "hi-IN-SwaraNeural",
    "hr": "hr-HR-GabrijelaNeural",
    "hu": "hu-HU-NoemiNeural",
    "hy": "hy-AM-AnahitNeural",
    "id": "id-ID-GadisNeural",
    "is": "is-IS-GudrunNeural",
    "it": "it-IT-ElsaNeural",
    "ja": "ja-JP-NanamiNeural",
    "jv": "jv-ID-SitiNeural",
    "ka": "ka-GE-EkaNeural",
    "kk": "kk-KZ-AigulNeural",
    "km": "km-KH-SreymomNeural",
    "kn": "kn-IN-SapnaNeural",
    "ko": "ko-KR-SunHiNeural",
    "lo": "lo-LA-KeomanyNeural",
    "lt": "lt-LT-OnaNeural",
    "lv": "lv-LV-EveritaNeural",
    "mk": "mk-MK-MarijaNeural",
    "ml": "ml-IN-SobhanaNeural",
    "mn": "mn-MN-YesunNeural",
    "mr": "mr-IN-AarohiNeural",
    "ms": "ms-MY-OsmanNeural",
    "mt": "mt-MT-GraceNeural",
    "my": "my-MM-NilarNeural",
    "ne": "ne-NP-HemkalaNeural",
    "nl": "nl-NL-ColetteNeural",
    "nb": "nb-NO-IselinNeural",
    "no": "nb-NO-IselinNeural",
    "pa": "pa-IN-GurpreetNeural",
    "pl": "pl-PL-ZofiaNeural",
    "ps": "ps-AF-LatifaNeural",
    "pt": "pt-BR-FranciscaNeural",
    "ro": "ro-RO-AlinaNeural",
    "ru": "ru-RU-SvetlanaNeural",
    "si": "si-LK-ThiliniNeural",
    "sk": "sk-SK-ViktoriaNeural",
    "sl": "sl-SI-PetraNeural",
    "so": "so-SO-UbaxNeural",
    "sq": "sq-AL-AnilaNeural",
    "sr": "sr-RS-SophieNeural",
    "sv": "sv-SE-HilleviNeural",
    "sw": "sw-KE-ZuriNeural",
    "ta": "ta-IN-PallaviNeural",
    "te": "te-IN-ShrutiNeural",
    "th": "th-TH-PremwadeeNeural",
    "tl": "tl-PH-MariaNeural",
    "tr": "tr-TR-EmelNeural",
    "uk": "uk-UA-OstapNeural",
    "ur": "ur-PK-UzmaNeural",
    "uz": "uz-UZ-MadinaNeural",
    "vi": "vi-VN-HoaiMyNeural",
    "zu": "zu-ZA-ThandoNeural",
}
# Chinese variants (langdetect can return "zh-cn", "zh-tw" or "zh")
TTS_VOICE_MAP["zh-cn"] = "zh-CN-XiaoxiaoNeural"
TTS_VOICE_MAP["zh-tw"] = "zh-TW-HsiaoChenNeural"
TTS_VOICE_MAP["zh"] = "zh-CN-XiaoxiaoNeural"


def _detect_language(text: str) -> str:
    """
    Detect language of text to choose TTS voice. Returns ISO 639-1 code (e.g. 'fa', 'tr', 'en', 'zh-cn').
    Uses langdetect when available; fallback to script-based heuristic.
    """
    text = text.strip()
    if not text or len(text) < 3:
        return "en"
    try:
        from langdetect import detect
        code = detect(text)
        if code:
            return code
    except Exception:
        pass
    # Fallback: count Arabic/Persian vs Latin script
    arabic_persian = sum(
        1
        for c in text
        if "\u0600" <= c <= "\u06FF"
        or "\uFB50" <= c <= "\uFDFF"
        or "\uFE70" <= c <= "\uFEFF"
    )
    latin = sum(
        1
        for c in text
        if c.isalpha() and (ord(c) < 0x0600 or ord(c) > 0x06FF)
    )
    if arabic_persian > latin:
        return "ar"
    return "en"


def _get_voice_for_language(
    text: str,
    voice_override: Optional[str] = None,
    lang_override: Optional[str] = None,
) -> str:
    """Return appropriate edge-tts voice based on detected or given language (50+ languages)."""
    if voice_override:
        return voice_override
    lang = (lang_override or "").strip().lower() or _detect_language(text)
    # Optional config overrides for specific languages
    if lang == "fa":
        return TTS_VOICE_FA
    if lang == "tr":
        return TTS_VOICE_TR
    return TTS_VOICE_MAP.get(lang) or TTS_VOICE_EN


async def text_to_speech_to_bytes(
    text: str,
    voice: Optional[str] = None,
    lang: Optional[str] = None,
) -> Optional[bytes]:
    """
    Synthesize text to MP3 audio in memory. Returns bytes or None on failure.
    Uses edge-tts (Microsoft online); detects language and picks neural voice (50+ languages).
    """
    if not text or not text.strip():
        return None
    voice_name = _get_voice_for_language(
        text, voice_override=voice, lang_override=lang
    )
    try:
        communicate = edge_tts.Communicate(text.strip(), voice_name)
        buffer = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio" and chunk.get("data"):
                buffer.write(chunk["data"])
        buffer.seek(0)
        return buffer.read()
    except Exception as e:
        logger.warning("edge-tts synthesis failed: %s", e, exc_info=True)
        return None
