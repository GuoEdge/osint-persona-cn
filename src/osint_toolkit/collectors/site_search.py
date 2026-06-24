"""通用站点 SERP 采集器 / Generic site:domain search collector."""

from __future__ import annotations

from osint_toolkit.collectors.base import BaseCollector
from osint_toolkit.collectors.serp.engine import SerpEngine, hits_to_items
from osint_toolkit.http.client import HttpClient
from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.utils.config import get_search_config


def build_site_collector(
    source_id: str,
    domain: str,
    *,
    fetch_content: bool = True,
) -> type[BaseCollector]:
    """为 source_catalog 中的站点条目动态生成 Collector 类。"""

    class _SiteCollector(BaseCollector):
        name = source_id
        _domain = domain

        def __init__(self, client: HttpClient | None = None) -> None:
            self._owns_client = client is None
            self.client = client or HttpClient()

        async def search(self, query: str, limit: int = 10) -> list[IntelItem]:
            engine = SerpEngine(client=self.client)
            hits, attempts = await engine.site_search(self._domain, query, limit=limit)
            items = hits_to_items(hits, source=self.name)
            seen: set[str] = set()
            deduped: list[IntelItem] = []
            for item in items:
                if item.url in seen:
                    continue
                seen.add(item.url)
                deduped.append(item)
            for it in deduped:
                it.personal["serp_attempts"] = attempts
                it.personal["site_domain"] = self._domain
            fetch_top = int(get_search_config().get("site_fetch_content_top", 3))
            if not fetch_content:
                fetch_top = 0
            if fetch_top > 0:
                from osint_toolkit.collectors.web import WebCollector

                web = WebCollector(self.client)
                enriched = 0
                for item in deduped:
                    if enriched >= fetch_top:
                        break
                    if len((item.content or "").strip()) >= 120 or not item.url:
                        continue
                    try:
                        full = await web.fetch(item.url)
                        if full.content and len(full.content) > len(item.content or ""):
                            item.content = full.content[:6000]
                            item.personal["content_fetched"] = True
                            enriched += 1
                    except Exception:  # noqa: BLE001
                        continue
            return deduped[:limit]

        async def fetch(self, url: str) -> IntelItem:
            from osint_toolkit.collectors.web import WebCollector

            item = await WebCollector(self.client).fetch(url)
            item.source = self.name
            return item

    _SiteCollector.__name__ = f"{source_id.title().replace('_', '')}Collector"
    _SiteCollector.__qualname__ = _SiteCollector.__name__
    return _SiteCollector
