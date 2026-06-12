"""去重 / Deduplication."""

from __future__ import annotations

from osint_toolkit.models.intel_item import IntelItem


def dedup_items(items: list[IntelItem]) -> list[IntelItem]:
    seen_urls: set[str] = set()
    result: list[IntelItem] = []
    for item in items:
        url_key = item.url.split("?")[0].rstrip("/")
        if url_key in seen_urls:
            continue
        seen_urls.add(url_key)
        result.append(item)
    return result
