"""Sanitize process proxy env so httpx-based clients can start.

Psiphon/V2Ray often export ALL_PROXY=socks://127.0.0.1:10808. httpx rejects the
`socks://` scheme (needs socks5:// + the optional socksio extra). That breaks
HuggingFace, Whisper downloads, Qdrant, and OpenAI-compatible SDKs.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_PROXY_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "SOCKS_PROXY",
    "SOCKS5_PROXY",
    "socks_proxy",
    "socks5_proxy",
)


def sanitize_proxy_env() -> list[str]:
    """Drop proxy URLs httpx cannot parse. Ensure localhost bypass. Returns removed keys."""
    removed: list[str] = []
    for key in _PROXY_KEYS:
        val = (os.environ.get(key) or "").strip()
        if not val:
            continue
        scheme = val.split("://", 1)[0].lower() if "://" in val else ""
        # httpx only accepts http/https/socks5/socks4 (socks4/5 need socksio).
        if scheme in {"socks", "socks5", "socks4", "socks5h", "socks4a"}:
            os.environ.pop(key, None)
            removed.append(f"{key}={val}")

    for key in ("NO_PROXY", "no_proxy"):
        existing = os.environ.get(key, "")
        parts = {p.strip() for p in existing.split(",") if p.strip()}
        parts.update({"127.0.0.1", "localhost", "::1"})
        os.environ[key] = ",".join(sorted(parts))

    if removed:
        logger.warning(
            "Removed unsupported SOCKS proxy env (httpx-incompatible): %s",
            ", ".join(removed),
        )
    return removed
