"""CLIP text and image embedding using transformers (openai/clip-vit-base-patch32).
Same model as old RAG; avoids sentence-transformers tokenizer issues.
Use run_in_executor when calling from async code."""
import io
import logging
import os
import time
from typing import List

import requests
from requests.exceptions import RequestException
import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

logger = logging.getLogger(__name__)

# Same as old RAG: 512-dim, text + image
CLIP_MODEL_ID = "openai/clip-vit-base-patch32"
CLIP_VECTOR_SIZE = 512

# Longer timeout for slow networks (HuggingFace download); 10 minutes
HF_DOWNLOAD_TIMEOUT_SEC = 600
# Retries for HuggingFace download (connection often drops on first try)
HF_LOAD_RETRIES = 3
HF_LOAD_RETRY_DELAY_SEC = 5
# If set to "1", no Hub requests (avoids Thread-auto_conversion timeout after load). Use when model is already cached.
# Example: set HF_HUB_OFFLINE=1 in env before starting the server to suppress the auto_conversion exception.

# Lazy-loaded state
_model = None
_processor = None
_device = None


def _load_with_retry(load_fn, name: str):
    """Call load_fn() with retries on OSError/RuntimeError (e.g. connection closed)."""
    last_err = None
    for attempt in range(1, HF_LOAD_RETRIES + 1):
        try:
            return load_fn()
        except (OSError, RuntimeError) as e:
            last_err = e
            if attempt < HF_LOAD_RETRIES:
                logger.warning(
                    "HuggingFace load %s failed (attempt %d/%d): %s. Retrying in %ds...",
                    name, attempt, HF_LOAD_RETRIES, e, HF_LOAD_RETRY_DELAY_SEC,
                )
                time.sleep(HF_LOAD_RETRY_DELAY_SEC)
            else:
                raise
    raise last_err


def get_embedder():
    """Return singleton CLIP embedder (sync). Uses transformers CLIPModel + CLIPProcessor."""
    global _model, _processor, _device
    if _model is None or _processor is None:
        try:
            # Avoid read timeout on slow connections (HuggingFace default is 10s)
            os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", str(HF_DOWNLOAD_TIMEOUT_SEC))
            logger.info("Loading CLIP model (%s)...", CLIP_MODEL_ID)
            _model = _load_with_retry(
                lambda: CLIPModel.from_pretrained(CLIP_MODEL_ID),
                "CLIPModel",
            )
            _processor = _load_with_retry(
                lambda: CLIPProcessor.from_pretrained(CLIP_MODEL_ID),
                "CLIPProcessor",
            )
            _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            if torch.cuda.is_available():
                logger.info("GPU detected: %s", torch.cuda.get_device_name(0))
                _model = _model.to(_device)
            _model.eval()
            logger.info("CLIP model loaded: %s (text + image)", CLIP_MODEL_ID)
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
    """پراکسی برای دانلود تصویر: اول IMAGE_FETCH_PROXY، بعد env HTTP(S)_PROXY."""
    from app.config import IMAGE_FETCH_PROXY
    if IMAGE_FETCH_PROXY:
        return {"http": IMAGE_FETCH_PROXY, "https": IMAGE_FETCH_PROXY}
    proxies = {}
    for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        val = os.environ.get(key)
        if val and val.strip():
            proxies.setdefault("https", val.strip())
            proxies.setdefault("http", val.strip())
            return proxies
    return None


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
