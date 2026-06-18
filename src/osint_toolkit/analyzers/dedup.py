"""去重 / Deduplication."""

from __future__ import annotations

import re

from osint_toolkit.models.intel_item import IntelItem

_TITLE_STRIP_RE = re.compile(r"[\s【】\[\]《》「」\-_|·:：,.，。!！?？（）()\"'“”]+")


def _url_key(url: str) -> str:
    return url.split("?")[0].split("#")[0].rstrip("/").lower()


def _title_key(title: str) -> str:
    t = _TITLE_STRIP_RE.sub("", (title or "").lower())
    return t[:80]


def _relevance(item: IntelItem) -> float:
    try:
        return float(item.signals.relevance or 0)
    except (TypeError, ValueError):
        return 0.0


def dedup_items(items: list[IntelItem]) -> list[IntelItem]:
    seen_urls: set[str] = set()
    title_best: dict[str, IntelItem] = {}
    result: list[IntelItem] = []
    for item in items:
        url_key = _url_key(item.url)
        if url_key in seen_urls:
            continue
        seen_urls.add(url_key)
        title_key = _title_key(item.title)
        if title_key and len(title_key) >= 6:
            existing = title_best.get(title_key)
            if existing is not None:
                if _relevance(item) <= _relevance(existing):
                    continue
                if existing in result:
                    result.remove(existing)
                title_best[title_key] = item
            else:
                title_best[title_key] = item
        result.append(item)
    return result
