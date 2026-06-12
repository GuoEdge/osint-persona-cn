"""RSS 采集器 / RSS collector."""

from __future__ import annotations

import feedparser

from osint_toolkit.collectors.base import BaseCollector
from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.utils.config import load_config


class RssCollector(BaseCollector):
    name = "rss"

    async def search(self, query: str, limit: int = 10) -> list[IntelItem]:
        feeds = load_config().get("rss_feeds", [])
        items: list[IntelItem] = []
        q = query.lower()
        for feed_url in feeds:
            parsed = feedparser.parse(feed_url)
            for entry in parsed.entries:
                title = entry.get("title", "")
                summary = entry.get("summary", "")
                if q and q not in (title + summary).lower():
                    continue
                items.append(
                    IntelItem(
                        source="rss",
                        type="article",
                        url=entry.get("link", ""),
                        title=title,
                        content=summary,
                        author=entry.get("author", ""),
                        published_at=entry.get("published"),
                    )
                )
                if len(items) >= limit:
                    return items[:limit]
        return items[:limit]

    async def fetch(self, url: str) -> IntelItem:
        from osint_toolkit.collectors.web import WebCollector

        return await WebCollector().fetch(url)
