"""SERP 编排引擎 / SERP orchestration engine."""

from __future__ import annotations

import os

from osint_toolkit.collectors.serp.models import SerpHit
from osint_toolkit.collectors.serp.providers import (
    API_PROVIDERS,
    HTML_PROVIDERS,
    PROVIDERS,
    _provider_delay,
)
from osint_toolkit.http.client import HttpClient
from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.utils.config import get_serp_config


def _auto_provider_order(cfg: dict) -> list[str]:
    order: list[str] = []
    if cfg.get("bing_api_key") or os.environ.get("BING_SEARCH_API_KEY"):
        order.append("bing_api")
    if cfg.get("serpapi_key") or os.environ.get("SERPAPI_KEY"):
        order.extend(["serpapi", "serpapi_baidu"])
    if cfg.get("searxng_base_url") or os.environ.get("SEARXNG_BASE_URL"):
        order.append("searxng")
    order.extend(["bing_html", "duckduckgo_html", "baidu_html", "sogou_html"])
    return order


def _provider_chain(cfg: dict) -> list[str]:
    primary = str(cfg.get("primary") or "auto").lower()
    fallbacks = [str(p).lower() for p in (cfg.get("fallbacks") or [])]
    if primary == "auto":
        chain = _auto_provider_order(cfg)
    else:
        chain = [primary]
    for fb in fallbacks:
        if fb not in chain:
            chain.append(fb)
    enabled = {str(p).lower() for p in (cfg.get("enabled_providers") or [])}
    if enabled:
        chain = [p for p in chain if p in enabled]
    return [p for p in chain if p in PROVIDERS]


def _dedupe_hits(hits: list[SerpHit], limit: int) -> list[SerpHit]:
    seen: set[str] = set()
    out: list[SerpHit] = []
    for hit in hits:
        url = hit.url.strip()
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(hit)
        if len(out) >= limit:
            break
    return out


class SerpEngine:
    def __init__(self, client: HttpClient | None = None) -> None:
        self.client = client or HttpClient()
        self.cfg = get_serp_config()

    async def _invoke(self, name: str, query: str, limit: int) -> tuple[list[SerpHit], str | None]:
        fn = PROVIDERS[name]
        if name in API_PROVIDERS:
            return await fn(self.client, query, limit, self.cfg)
        return await fn(self.client, query, limit, self.cfg)

    async def search(self, query: str, limit: int = 10) -> tuple[list[SerpHit], list[str]]:
        """按配置链尝试各 SERP 提供方，返回 hits 与尝试日志。"""
        chain = _provider_chain(self.cfg)
        strategy = str(self.cfg.get("strategy") or "fallback").lower()
        attempts: list[str] = []

        if strategy == "merge_html":
            return await self._search_merge_html(query, limit, chain, attempts)

        for name in chain:
            await _provider_delay(self.cfg)
            hits, err = await self._invoke(name, query, limit)
            if hits:
                attempts.append(f"{name}: ok ({len(hits)})")
                return hits[:limit], attempts
            attempts.append(err or f"{name}: empty")
        return [], attempts

    async def _search_merge_html(
        self,
        query: str,
        limit: int,
        chain: list[str],
        attempts: list[str],
    ) -> tuple[list[SerpHit], list[str]]:
        """API 优先；HTML 引擎结果合并去重，提高召回。"""
        merged: list[SerpHit] = []
        merge_min = int(self.cfg.get("merge_min_hits") or max(3, limit // 2))

        for name in chain:
            if name not in API_PROVIDERS:
                continue
            await _provider_delay(self.cfg)
            hits, err = await self._invoke(name, query, limit)
            if hits:
                attempts.append(f"{name}: ok ({len(hits)})")
                return hits[:limit], attempts
            attempts.append(err or f"{name}: empty")

        html_chain = [n for n in chain if n in HTML_PROVIDERS]
        for name in html_chain:
            await _provider_delay(self.cfg)
            hits, err = await self._invoke(name, query, limit)
            if hits:
                merged.extend(hits)
                attempts.append(f"{name}: ok ({len(hits)})")
            else:
                attempts.append(err or f"{name}: empty")
            if len(_dedupe_hits(merged, limit * 2)) >= merge_min:
                break

        deduped = _dedupe_hits(merged, limit)
        return deduped, attempts

    async def site_search(self, domain: str, query: str, limit: int = 10) -> tuple[list[SerpHit], list[str]]:
        site_query = f"site:{domain} {query}".strip()
        hits, attempts = await self.search(site_query, limit=limit)
        for h in hits:
            h.meta["site"] = domain
        return hits, attempts


async def site_search(query: str, domain: str, limit: int = 10, client: HttpClient | None = None) -> list[SerpHit]:
    engine = SerpEngine(client=client)
    hits, _ = await engine.site_search(domain, query, limit=limit)
    return hits


def hits_to_items(hits: list[SerpHit], *, source: str = "web") -> list[IntelItem]:
    items: list[IntelItem] = []
    seen: set[str] = set()
    for hit in hits:
        url = hit.url.strip()
        if not url or url in seen:
            continue
        seen.add(url)
        item = IntelItem(
            source=source,
            type="snippet",
            url=url,
            title=hit.title,
            content=hit.snippet,
        )
        item.personal["serp_engine"] = hit.engine
        item.personal["serp_query"] = hit.query
        if hit.meta.get("site"):
            item.personal["site_search"] = hit.meta["site"]
        if hit.meta.get("source_engine"):
            item.personal["searxng_source"] = hit.meta["source_engine"]
        items.append(item)
    return items
