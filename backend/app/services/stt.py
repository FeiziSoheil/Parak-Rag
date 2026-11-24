"""Speech-to-Text using faster-whisper. Singleton model; int8 for GPU/CPU to avoid OOM on limited VRAM."""
# reload trigger
import logging
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any, Optional

from app.config import WHISPER_MODEL_SIZE

logger = logging.getLogger(__name__)

# Sample rate Whisper expects; conversion uses this.
WHISPER_SAMPLE_RATE = 16000


def _preload_cuda12_libs() -> list[str]:
    """Preload CUDA 12 user-space libs (libcublas.so.12) shipped in pip nvidia-* wheels.

    ctranslate2 4.x links against libcublas.so.12 (CUDA 12). If torch is a cu13x
    build, only CUDA 13 libs (libcublas.so.13) exist on the loader path and
    ctranslate2 fails at first inference with
    'RuntimeError: Library libcublas.so.12 is not found or cannot be loaded'.
    Loading the cu12 wheels explicitly via ctypes fixes resolution without
    touching system CUDA. Must run before the first CUDA inference.
    """
    import ctypes
    import site

    loaded: list[str] = []
    wanted = ("libcublasLt.so.12", "libcublas.so.12")  # Lt first: cublas depends on it

    bases: list[Path] = []
    try:
        bases.extend(Path(sp) / "nvidia" for sp in site.getsitepackages())
    except Exception:
        pass
    venv_sp = Path(__file__).resolve().parents[2] / "venv" / "lib"
    if venv_sp.is_dir():
        for sp in venv_sp.glob("python3*/site-packages"):
            bases.append(sp / "nvidia")

    seen: set[str] = set()
    for base in bases:
        if not base.is_dir():
            continue
        for lib_dir in sorted(base.glob("*/lib")):
            for name in wanted:
                if name in seen:
                    continue
                so = lib_dir / name
                if so.exists():
                    try:
                        ctypes.CDLL(str(so), mode=ctypes.RTLD_GLOBAL)
                        loaded.append(name)
                        seen.add(name)
                        logger.info("Preloaded %s from %s", name, lib_dir)
                    except OSError as e:
                        logger.warning("Could not preload %s: %s", so, e)
        if len(seen) == len(wanted):
            break
    return loaded

# Lock for thread-safe model loading
_model_lock = threading.Lock()


def _get_ffmpeg_path() -> Optional[str]:
    """Resolve ffmpeg executable: FFMPEG_PATH env first, then PATH via shutil.which."""
    explicit = os.getenv("FFMPEG_PATH", "").strip()
    if explicit and Path(explicit).exists():
        return explicit
    return shutil.which("ffmpeg")


def convert_to_wav_16k(source_path: str) -> Optional[str]:
    """
    Convert any audio file (e.g. WebM/Opus from browser) to 16kHz mono WAV so Whisper decodes reliably.
    Uses ffmpeg if available. Returns path to temporary WAV file, or None on failure (caller can use source_path).
    """
    path = Path(source_path)
    if not path.exists() or not path.is_file():
        return None
    ffmpeg_cmd = _get_ffmpeg_path()
    if not ffmpeg_cmd:
        logger.warning(
            "ffmpeg not found (set FFMPEG_PATH to full path, e.g. C:\\ffmpeg\\...\\bin\\ffmpeg.exe, or add ffmpeg to PATH)"
        )
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
                ffmpeg_cmd,
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
_model_loading: bool = False
_force_cpu: bool = False


def get_whisper_model() -> tuple[Any, str, str]:
    """Load Whisper model once (Singleton). Tries CUDA first, then CPU; both use int8.
    Thread-safe: uses lock to prevent multiple concurrent loads."""
    global _model, _device, _compute_type, _model_loading
    
    # Fast path: model already loaded
    if _model is not None:
        return _model, _device, _compute_type

    with _model_lock:
        # Double-check after acquiring lock
        if _model is not None:
            return _model, _device, _compute_type
        
        if _model_loading:
            logger.warning("Whisper model is still loading from another thread, waiting...")
            # Wait for the other thread to finish loading
            while _model_loading and _model is None:
                import time
                time.sleep(0.5)
            if _model is not None:
                return _model, _device, _compute_type
        
        _model_loading = True
        
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            _model_loading = False
            raise RuntimeError(
                "faster-whisper is not installed. Install with: pip install faster-whisper"
            ) from e

        size = WHISPER_MODEL_SIZE.strip().lower()
        if size not in ("tiny", "base", "small", "medium", "large-v2", "large-v3"):
            size = "small"
        compute = "int8"

        # Try CUDA first (skipped when a previous CUDA inference failed and forced CPU)
        try:
            import torch
            if not _force_cpu and torch.cuda.is_available():
                # ctranslate2 needs CUDA 12 libs (libcublas.so.12); torch cu13x
                # builds only expose .so.13, so preload cu12 wheels explicitly.
                _preload_cuda12_libs()
                logger.info("Loading Whisper model (%s) on CUDA with compute_type=%s...", size, compute)
                _model = WhisperModel(size, device="cuda", compute_type=compute)
                _device = "cuda"
                _compute_type = compute
                logger.info("Whisper loaded on CUDA: %s", torch.cuda.get_device_name(0))
                _model_loading = False
                return _model, _device, _compute_type
        except Exception as e:
            logger.warning("Whisper CUDA load failed, falling back to CPU: %s", e)

        # Fallback to CPU
        logger.info("Loading Whisper model (%s) on CPU with compute_type=%s...", size, compute)
        _model = WhisperModel(size, device="cpu", compute_type=compute)
        _device = "cpu"
        _compute_type = compute
        logger.info("Whisper loaded on CPU")
        _model_loading = False
        return _model, _device, _compute_type


def transcribe_audio(audio_path: str) -> str:
    """
    Transcribe audio file to text using the singleton Whisper model.
    Call from async code via run_in_executor.
    Prefer converting WebM/Opus to WAV before calling to avoid "Error parsing Opus packet header".
    """
    wav_path = convert_to_wav_16k(audio_path)
    path_to_use = wav_path if wav_path else audio_path
    try:
        return _transcribe_with_fallback(path_to_use)
    finally:
        if wav_path and Path(wav_path).exists():
            try:
                Path(wav_path).unlink()
            except OSError:
                pass


def _transcribe_with_fallback(path_to_use: str) -> str:
    """Transcribe; on CUDA runtime failure reload the singleton on CPU and retry once.

    Keeps /api/voice-chat from 500-ing when GPU libs are broken (e.g. missing
    libcublas.so.12): first failure flips _force_cpu so every later call uses CPU.
    """
    global _model, _force_cpu

    def _run(model: Any) -> str:
        segments, _ = model.transcribe(path_to_use, language=None, vad_filter=True)
        parts = [s.text.strip() for s in segments if s.text and s.text.strip()]
        return " ".join(parts).strip() if parts else ""

    model, device, _ = get_whisper_model()
    try:
        return _run(model)
    except Exception as e:
        if device != "cuda":
            raise
        logger.error("CUDA transcription failed (%s: %s); falling back to CPU", type(e).__name__, e)
        with _model_lock:
            _model = None
            _force_cpu = True
        model, device, _ = get_whisper_model()
        logger.info("Whisper reloaded on %s after CUDA failure", device)
        return _run(model)
