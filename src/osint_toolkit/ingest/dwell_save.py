"""高停留自动收录 / Auto-save to knowledge on high dwell time."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from osint_toolkit.utils.config import load_config

_SAVEABLE = (
    re.compile(r"bilibili\.com/video/(BV[\w]+|av\d+)", re.I),
    re.compile(r"zhihu\.com/question/\d+", re.I),
    re.compile(r"zhihu\.com/p/\d+", re.I),
    re.compile(r"zhuanlan\.zhihu\.com/p/\d+", re.I),
    re.compile(r"github\.com/[^/]+/[^/?#]+", re.I),
    re.compile(r"v2ex\.com/t/\d+", re.I),
    re.compile(r"juejin\.cn/post/\d+", re.I),
    re.compile(r"sspai\.com/post/\d+", re.I),
    re.compile(r"huxiu\.com/article/\d+", re.I),
    re.compile(r"36kr\.com/p/\d+", re.I),
    re.compile(r"xiaohongshu\.com/explore/[a-f0-9]+", re.I),
    re.compile(r"weibo\.com/\d+/[A-Za-z0-9]+", re.I),
    re.compile(r"douban\.com/(subject|review|note)/\d+", re.I),
)

_SKIP_FRAGMENTS = (
    "/account/",
    "/settings",
    "/search?",
    "/login",
    "/signin",
    "/notifications",
    "/messages",
    "/collections/mine",
)


def dwell_save_config() -> dict[str, Any]:
    cfg = load_config().get("extension", {})
    return {
        "enabled": bool(cfg.get("dwell_save_enabled", True)),
        "dwell_ms": int(cfg.get("dwell_save_ms", 90_000)),
    }


def is_saveable_content_url(url: str) -> bool:
    if not url.startswith("http"):
        return False
    lower = url.lower()
    if any(s in lower for s in _SKIP_FRAGMENTS):
        return False
    host_path = urlparse(url).netloc + urlparse(url).path
    return any(p.search(host_path) or p.search(lower) for p in _SAVEABLE)


def collect_dwell_save_urls(payloads: list[dict[str, Any]]) -> list[str]:
    cfg = dwell_save_config()
    if not cfg["enabled"]:
        return []
    threshold = cfg["dwell_ms"]
    seen: set[str] = set()
    urls: list[str] = []
    for payload in payloads:
        if payload.get("kind") != "page_session":
            continue
        duration_ms = int(payload.get("duration_ms") or 0)
        if duration_ms < threshold:
            continue
        url = str(payload.get("url") or "")
        if not is_saveable_content_url(url) or url in seen:
            continue
        seen.add(url)
        urls.append(url)
    return urls


def knowledge_auto_dedup_key(url: str) -> str:
    return f"knowledge_auto|{url}"
