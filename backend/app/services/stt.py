"""Speech-to-Text using faster-whisper. Singleton model; int8 for GPU/CPU to avoid OOM on limited VRAM."""
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

from app.config import WHISPER_MODEL_SIZE

logger = logging.getLogger(__name__)

# Sample rate Whisper expects; conversion uses this.
WHISPER_SAMPLE_RATE = 16000


def convert_to_wav_16k(source_path: str) -> Optional[str]:
    """
    Convert any audio file (e.g. WebM/Opus from browser) to 16kHz mono WAV so Whisper decodes reliably.
    Uses ffmpeg if available. Returns path to temporary WAV file, or None on failure (caller can use source_path).
    """
    path = Path(source_path)
    if not path.exists() or not path.is_file():
        return None
    try:
        out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        out.close()
        out_path = out.name
    except Exception as e:
        logger.warning("Could not create temp file for WAV conversion: %s", e)
        return None
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i", str(path),
                "-acodec", "pcm_s16le",
                "-ar", str(WHISPER_SAMPLE_RATE),
                "-ac", "1",
                out_path,
            ],
            capture_output=True,
            timeout=30,
            check=True,
        )
        return out_path
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning("ffmpeg conversion failed (%s), will try original file: %s", type(e).__name__, e)
        try:
            Path(out_path).unlink(missing_ok=True)
        except OSError:
            pass
        return None

_model: Any = None
_device: str = "cpu"
_compute_type: str = "int8"


def get_whisper_model() -> tuple[Any, str, str]:
    """Load Whisper model once (Singleton). Tries CUDA first, then CPU; both use int8."""
    global _model, _device, _compute_type
    if _model is not None:
        return _model, _device, _compute_type

    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError(
            "faster-whisper is not installed. Install with: pip install faster-whisper"
        ) from e

    size = WHISPER_MODEL_SIZE.strip().lower()
    if size not in ("tiny", "base", "small", "medium", "large-v2", "large-v3"):
        size = "small"
    compute = "int8"

    # Try CUDA first
    try:
        import torch
        if torch.cuda.is_available():
            logger.info("Loading Whisper model (%s) on CUDA with compute_type=%s...", size, compute)
            _model = WhisperModel(size, device="cuda", compute_type=compute)
            _device = "cuda"
            _compute_type = compute
            logger.info("Whisper loaded on CUDA: %s", torch.cuda.get_device_name(0))
            return _model, _device, _compute_type
    except Exception as e:
        logger.warning("Whisper CUDA load failed, falling back to CPU: %s", e)

    # Fallback to CPU
    logger.info("Loading Whisper model (%s) on CPU with compute_type=%s...", size, compute)
    _model = WhisperModel(size, device="cpu", compute_type=compute)
    _device = "cpu"
    _compute_type = compute
    logger.info("Whisper loaded on CPU")
    return _model, _device, _compute_type


def transcribe_audio(audio_path: str) -> str:
    """
    Transcribe audio file to text using the singleton Whisper model.
    Call from async code via run_in_executor.
    Prefer converting WebM/Opus to WAV before calling to avoid "Error parsing Opus packet header".
    """
    model, _, _ = get_whisper_model()
    wav_path = convert_to_wav_16k(audio_path)
    path_to_use = wav_path if wav_path else audio_path
    try:
        segments, _ = model.transcribe(path_to_use, language=None, vad_filter=True)
        parts = [s.text.strip() for s in segments if s.text and s.text.strip()]
        return " ".join(parts).strip() if parts else ""
    finally:
        if wav_path and Path(wav_path).exists():
            try:
                Path(wav_path).unlink()
            except OSError:
                pass
