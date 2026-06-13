"""SERP 结果 URL 归一化 / Normalize redirect-wrapped result URLs."""

from __future__ import annotations

import base64
import re
from urllib.parse import parse_qs, unquote, urlparse

_BING_U_RE = re.compile(r"[?&]u=([^&]+)")


def normalize_result_url(url: str) -> str:
    """展开 Bing/Baidu 跳转链接，返回目标 URL。"""
    raw = (url or "").strip()
    if not raw:
        return raw
    lowered = raw.lower()
    if "baidu.com/link" in lowered:
        return _unwrap_baidu_link(raw) or raw
    if "bing.com/ck/a" in lowered:
        return _unwrap_bing_link(raw) or raw
    return raw


def _unwrap_baidu_link(url: str) -> str | None:
    parsed = urlparse(url)
    target = (parse_qs(parsed.query).get("url") or [None])[0]
    if not target:
        return None
    return unquote(target)


def _unwrap_bing_link(url: str) -> str | None:
    match = _BING_U_RE.search(url)
    if not match:
        return None
    token = unquote(match.group(1))
    # Bing 常见两种编码：a1<base64> 或纯 base64
    payload = token[2:] if token.startswith("a1") else token
    try:
        padded = payload + "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(padded).decode("utf-8", errors="ignore")
        if decoded.startswith("http"):
            return decoded
    except Exception:  # noqa: BLE001
        pass
    if token.startswith("http"):
        return token
    return None
