"""CLIP text and image embedding using transformers (openai/clip-vit-base-patch32).
Same model as old RAG; avoids sentence-transformers tokenizer issues.
Use run_in_executor when calling from async code."""
import io
import logging
import os
import time
import urllib3
from typing import List

import requests
from requests.exceptions import RequestException
import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

# Suppress SSL warnings if verify is disabled
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

# Same as old RAG: 512-dim, text + image
CLIP_MODEL_ID = "openai/clip-vit-base-patch32"
CLIP_VECTOR_SIZE = 512

# Longer timeout for slow networks (HuggingFace download); 15 minutes
HF_DOWNLOAD_TIMEOUT_SEC = 900
# Retries for HuggingFace download (connection often drops on first try)
HF_LOAD_RETRIES = 5
HF_LOAD_RETRY_DELAY_SEC = 3
# Exponential backoff multiplier
HF_LOAD_RETRY_BACKOFF = 1.5
# If set to "1", no Hub requests (avoids Thread-auto_conversion timeout after load). Use when model is already cached.
# Example: set HF_HUB_OFFLINE=1 in env before starting the server to suppress the auto_conversion exception.

# Lazy-loaded state
_model = None
_processor = None
_device = None


def _load_with_retry(load_fn, name: str):
    """Call load_fn() with retries on OSError/RuntimeError (e.g. connection closed).
    Uses exponential backoff to handle transient network failures."""
    last_err = None
    retry_delay = HF_LOAD_RETRY_DELAY_SEC
    
    for attempt in range(1, HF_LOAD_RETRIES + 1):
        try:
            logger.info("Loading %s (attempt %d/%d)...", name, attempt, HF_LOAD_RETRIES)
            return load_fn()
        except (OSError, RuntimeError, requests.exceptions.RequestException, urllib3.exceptions.HTTPError) as e:
            last_err = e
            if attempt < HF_LOAD_RETRIES:
                logger.warning(
                    "HuggingFace load %s failed (attempt %d/%d): %s. Retrying in %.1fs...",
                    name, attempt, HF_LOAD_RETRIES, str(e)[:100], retry_delay,
                )
                time.sleep(retry_delay)
                retry_delay *= HF_LOAD_RETRY_BACKOFF  # Exponential backoff
            else:
                logger.error(
                    "HuggingFace load %s failed after %d attempts. Last error: %s",
                    name, HF_LOAD_RETRIES, e,
                )
                raise
    raise last_err


def get_embedder():
    """Return singleton CLIP embedder (sync). Uses transformers CLIPModel + CLIPProcessor."""
    global _model, _processor, _device
    if _model is None or _processor is None:
        try:
            # Avoid read timeout on slow connections (HuggingFace default is 10s)
            hf_timeout = os.environ.get("HF_HUB_DOWNLOAD_TIMEOUT", str(HF_DOWNLOAD_TIMEOUT_SEC))
            os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", hf_timeout)
            
            # Check if offline mode is enabled
            offline_mode = os.environ.get("HF_HUB_OFFLINE", "0") == "1"
            if offline_mode:
                logger.info("HuggingFace offline mode enabled; will use cached models only")
                os.environ["HF_HUB_OFFLINE"] = "1"
            
            logger.info("Loading CLIP model (%s) with timeout=%s...", CLIP_MODEL_ID, hf_timeout)
            _model = _load_with_retry(
                lambda: CLIPModel.from_pretrained(
                    CLIP_MODEL_ID,
                    local_files_only=offline_mode,
                ),
                "CLIPModel",
            )
            _processor = _load_with_retry(
                lambda: CLIPProcessor.from_pretrained(
                    CLIP_MODEL_ID,
                    local_files_only=offline_mode,
                ),
                "CLIPProcessor",
            )
            _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            if torch.cuda.is_available():
                logger.info("GPU detected: %s", torch.cuda.get_device_name(0))
                _model = _model.to(_device)
            _model.eval()
            logger.info("CLIP model loaded successfully: %s (text + image)", CLIP_MODEL_ID)
        except Exception as e:
            _model = None
            _processor = None
            _device = None
            logger.exception("CLIP embedder load failed")
            raise RuntimeError(f"CLIP embedder failed to load: {e}. Check network or retry.") from e
    return {"model": _model, "processor": _processor, "device": _device}


def _embedder_supports_images() -> bool:
    """True: we only use CLIP, which supports both text and images."""
    return True


def get_embedding_dim() -> int:
    """Return vector dimension (512 for openai/clip-vit-base-patch32)."""
    return CLIP_VECTOR_SIZE


def _to_tensor(feats):
    """Extract tensor from get_text_features/get_image_features (may return tensor or output object)."""
    if torch.is_tensor(feats):
        return feats
    if hasattr(feats, "pooler_output") and feats.pooler_output is not None:
        return feats.pooler_output
    if hasattr(feats, "last_hidden_state"):
        return feats.last_hidden_state[:, 0, :]
    raise TypeError(f"Unexpected features type: {type(feats)}")


def _encode_text_single(text: str) -> List[float]:
    """Encode one text to L2-normalized 512-dim vector."""
    emb = get_embedder()
    model, processor, device = emb["model"], emb["processor"], emb["device"]
    if processor is None:
        raise RuntimeError("CLIP processor not loaded. Restart the app or check network and retry.")
    inputs = processor(text=text, return_tensors="pt", padding=True, truncation=True)
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.no_grad():
        out = model.get_text_features(**inputs)
        feats = _to_tensor(out)
        feats = feats / feats.norm(p=2, dim=-1, keepdim=True)
    return feats.squeeze().cpu().numpy().tolist()


def embed_text(text: str) -> List[float]:
    """Embed single text. Returns list of 512 floats."""
    return _encode_text_single(text)


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Embed list of texts. Returns list of vectors of length get_embedding_dim()."""
    if not texts:
        return []
    emb = get_embedder()
    model, processor, device = emb["model"], emb["processor"], emb["device"]
    if processor is None:
        raise RuntimeError("CLIP processor not loaded. Restart the app or check network and retry.")
    inputs = processor(text=texts, return_tensors="pt", padding=True, truncation=True)
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.no_grad():
        out = model.get_text_features(**inputs)
        feats = _to_tensor(out)
        feats = feats / feats.norm(p=2, dim=-1, keepdim=True)
    return feats.cpu().numpy().tolist()


def _get_image_request_proxies():
    """پراکسی فقط وقتی IMAGE_FETCH_PROXY در .env تنظیم شده باشد؛ وگرنه مستقیم (بدون env HTTP_PROXY)."""
    from app.config import IMAGE_FETCH_PROXY
    if IMAGE_FETCH_PROXY:
        return {"http": IMAGE_FETCH_PROXY, "https": IMAGE_FETCH_PROXY}
    return {"http": None, "https": None}


# شبیه مرورگر تا CDN (مثل علی‌اکسپرس) اتصال را قطع نکند
IMAGE_REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
}


def embed_image_url(url: str) -> List[float]:
    """Download image from URL and embed. Returns 512-dim vector."""
    emb = get_embedder()
    model, processor, device = emb["model"], emb["processor"], emb["device"]
    if processor is None:
        raise RuntimeError("CLIP processor not loaded. Restart the app or check network and retry.")
    proxies = _get_image_request_proxies()
    last_err = None
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=20, proxies=proxies, headers=IMAGE_REQUEST_HEADERS)
            resp.raise_for_status()
            break
        except RequestException as e:
            last_err = e
            if attempt < 2:
                time.sleep(1.0 * (attempt + 1))
            else:
                raise
    img = Image.open(io.BytesIO(resp.content)).convert("RGB")
    inputs = processor(images=img, return_tensors="pt")
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.no_grad():
        out = model.get_image_features(**inputs)
        feats = _to_tensor(out)
        feats = feats / feats.norm(p=2, dim=-1, keepdim=True)
    return feats.squeeze().cpu().numpy().tolist()


def embed_image_bytes(data: bytes) -> List[float]:
    """Embed image from bytes (e.g. uploaded file). Returns 512-dim vector."""
    emb = get_embedder()
    model, processor, device = emb["model"], emb["processor"], emb["device"]
    if processor is None:
        raise RuntimeError("CLIP processor not loaded. Restart the app or check network and retry.")
    img = Image.open(io.BytesIO(data)).convert("RGB")
    inputs = processor(images=img, return_tensors="pt")
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.no_grad():
        out = model.get_image_features(**inputs)
        feats = _to_tensor(out)
        feats = feats / feats.norm(p=2, dim=-1, keepdim=True)
    return feats.squeeze().cpu().numpy().tolist()
