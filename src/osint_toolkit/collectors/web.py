"""Web 搜索采集器 / Web search collector."""

from __future__ import annotations

import asyncio

from osint_toolkit.collectors.base import BaseCollector
from osint_toolkit.collectors.serp.engine import SerpEngine, hits_to_items
from osint_toolkit.http.client import HttpClient
from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.utils.config import get_serp_config


class WebCollector(BaseCollector):
    name = "web"

    def __init__(self, client: HttpClient | None = None) -> None:
        self.client = client or HttpClient()

    async def search(self, query: str, limit: int = 10) -> list[IntelItem]:
        cfg = get_serp_config()
        engine = SerpEngine(client=self.client)
        hits, attempts = await engine.search(query, limit=limit)
        for domain in cfg.get("site_searches") or []:
            site_hits, site_attempts = await engine.site_search(str(domain), query, limit=max(3, limit // 2))
            hits.extend(site_hits)
            attempts.extend(site_attempts)
        items = hits_to_items(hits, source="web")
        if not items:
            return [
                IntelItem(
                    source="web",
                    type="search_link",
                    url=f"serp://{query}",
                    title=f"Web搜索: {query}",
                    content="; ".join(attempts[-3:]) if attempts else "Web 搜索无结果",
                )
            ]
        seen: set[str] = set()
        deduped: list[IntelItem] = []
        for item in items:
            if item.url in seen:
                continue
            seen.add(item.url)
            deduped.append(item)
        items = deduped[:limit]
        for it in items:
            it.personal["serp_attempts"] = attempts
        if cfg.get("web_fetch_content", True):
            top_n = int(cfg.get("web_fetch_top") or 5)
            await self._enrich_content(items[:top_n])
        return items

    async def _enrich_content(self, items: list[IntelItem]) -> None:
        async def enrich_one(item: IntelItem) -> None:
            if not item.url.startswith("http"):
                return
            try:
                fetched = await self.fetch(item.url)
                if fetched.content:
                    item.content = fetched.content[:8000]
                if fetched.title and len(fetched.title) > 2:
                    item.title = fetched.title
                item.personal["content_fetched"] = True
            except Exception:  # noqa: BLE001
                item.personal["content_fetched"] = False

        await asyncio.gather(*[enrich_one(i) for i in items])

    async def fetch(self, url: str) -> IntelItem:
        import re

        text = await self.client.get_text(url)
        title_match = re.search(r"<title>(.*?)</title>", text, re.I | re.S)
        title = title_match.group(1).strip() if title_match else url
        from osint_toolkit.processors.normalize import extract_text_from_html

        content = extract_text_from_html(text)[:8000]
        return IntelItem(source="web", type="article", url=url, title=title, content=content)
