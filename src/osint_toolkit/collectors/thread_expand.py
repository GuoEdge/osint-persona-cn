"""论坛帖正文加深 / Enrich forum thread snippets."""

from __future__ import annotations

from osint_toolkit.collectors.web import WebCollector
from osint_toolkit.http.client import HttpClient
from osint_toolkit.models.intel_item import IntelItem

FORUM_SOURCES: set[str] = {"nga", "tieba", "reddit", "v2ex"}


async def enrich_forum_threads(
    items: list[IntelItem],
    *,
    client: HttpClient | None = None,
    top: int = 5,
    min_snippet: int = 80,
) -> list[IntelItem]:
    """对论坛类 SERP 摘要过短的条目抓取正文前几段。"""
    owns = client is None
    client = client or HttpClient()
    web = WebCollector(client)
    try:
        count = 0
        for item in items:
            if count >= top:
                break
            if item.source not in FORUM_SOURCES:
                continue
            if len((item.content or "").strip()) >= min_snippet:
                continue
            if not item.url:
                continue
            try:
                full = await web.fetch(item.url)
                if full.content and len(full.content) > len(item.content or ""):
                    item.content = full.content[:8000]
                    item.personal["forum_enriched"] = True
                    count += 1
            except Exception:  # noqa: BLE001
                continue
        return items
    finally:
        if owns:
            await client.aclose()
