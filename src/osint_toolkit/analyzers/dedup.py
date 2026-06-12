"""去重 / Deduplication."""

from __future__ import annotations

from osint_toolkit.models.intel_item import IntelItem


def dedup_items(items: list[IntelItem]) -> list[IntelItem]:
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    result: list[IntelItem] = []
    for item in items:
        url_key = item.url.split("?")[0].rstrip("/")
        title_key = item.title.strip().lower()[:80]
        if url_key in seen_urls:
            continue
        if title_key and title_key in seen_titles:
            continue
        seen_urls.add(url_key)
        if title_key:
            seen_titles.add(title_key)
        result.append(item)
    return result
