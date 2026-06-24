"""SERP 编排引擎 / SERP orchestration engine."""

from __future__ import annotations

import asyncio
import os

import httpx

from osint_toolkit.collectors.serp.cache import get_cached, set_cached
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

_DEFAULT_PROVIDER_WEIGHTS: dict[str, int] = {
    "bing_api": 5,
    "serpapi": 4,
    "serpapi_baidu": 3,
    "searxng": 3,
    "bing_html": 4,
    "sogou_html": 2,
    "duckduckgo_html": 2,
    "baidu_html": 1,
}


def _has_api_keys(cfg: dict) -> bool:

    return bool(
        cfg.get("bing_api_key")
        or cfg.get("serpapi_key")
        or cfg.get("searxng_base_url")
        or os.environ.get("BING_SEARCH_API_KEY")
        or os.environ.get("SERPAPI_KEY")
        or os.environ.get("SEARXNG_BASE_URL")
    )


def _auto_provider_order(cfg: dict) -> list[str]:

    order: list[str] = []

    if cfg.get("bing_api_key") or os.environ.get("BING_SEARCH_API_KEY"):
        order.append("bing_api")

    if cfg.get("serpapi_key") or os.environ.get("SERPAPI_KEY"):
        order.extend(["serpapi", "serpapi_baidu"])

    if cfg.get("searxng_base_url") or os.environ.get("SEARXNG_BASE_URL"):
        order.append("searxng")

    # Bing 权重更高，HTML 引擎并行合并时优先保留 Bing 结果

    order.extend(["bing_html", "sogou_html", "duckduckgo_html", "baidu_html"])

    return order


def _provider_weights(cfg: dict) -> dict[str, int]:

    weights = dict(_DEFAULT_PROVIDER_WEIGHTS)

    custom = cfg.get("provider_weights") or {}

    if isinstance(custom, dict):
        for key, val in custom.items():
            try:
                weights[str(key)] = int(val)

            except (TypeError, ValueError):
                continue

    return weights


def _format_provider_error(name: str, exc: BaseException) -> str:

    msg = str(exc).strip() or exc.__class__.__name__

    if "connection attempts failed" in msg.lower() or isinstance(exc, httpx.ConnectError):
        return f"{name}: 网络连接失败（可配置 http.proxy 或检查代理/VPN）"

    if isinstance(exc, httpx.TimeoutException):
        return f"{name}: 请求超时"

    return f"{name}: {msg[:120]}"


def _effective_strategy(cfg: dict) -> str:

    strategy = str(cfg.get("strategy") or "fallback").lower()

    if strategy == "auto":
        # 默认并行合并 HTML 引擎，提高召回；有 API 时仍先尝试 API

        return "merge_html"

    return strategy


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


def _rank_hits_by_weight(hits: list[SerpHit], weights: dict[str, int], limit: int) -> list[SerpHit]:

    indexed = list(enumerate(hits))

    indexed.sort(key=lambda pair: (-weights.get(pair[1].engine, 0), pair[0]))

    return _dedupe_hits([hit for _, hit in indexed], limit)


class SerpEngine:
    def __init__(self, client: HttpClient | None = None) -> None:

        self._owns_client = client is None
        self.client = client or HttpClient()

        self.cfg = get_serp_config()

    async def _invoke(self, name: str, query: str, limit: int) -> tuple[list[SerpHit], str | None]:

        fn = PROVIDERS[name]

        try:
            return await fn(self.client, query, limit, self.cfg)

        except (httpx.ConnectError, httpx.TimeoutException, OSError) as exc:
            return [], _format_provider_error(name, exc)

    async def search(self, query: str, limit: int = 10) -> tuple[list[SerpHit], list[str]]:
        """按配置链尝试各 SERP 提供方，返回 hits 与尝试日志。"""

        chain = _provider_chain(self.cfg)

        strategy = _effective_strategy(self.cfg)

        attempts: list[str] = []

        ttl = int(self.cfg.get("cache_ttl_sec") or 0)

        cache_key = f"{strategy}|{query.strip().lower()}|{limit}"

        if ttl > 0:
            cached = get_cached(cache_key, ttl)

            if cached:
                hits, cache_attempts = cached

                if hits:
                    return hits[:limit], [f"cache: ok ({len(hits)})"] + cache_attempts

        if strategy == "merge_html":
            hits, attempts = await self._search_merge_html(query, limit, chain, attempts)

        else:
            hits, attempts = await self._search_fallback(query, limit, chain, attempts)

        if hits and ttl > 0:
            set_cached(cache_key, hits[:limit], attempts)

        return hits, attempts

    async def _search_fallback(
        self,
        query: str,
        limit: int,
        chain: list[str],
        attempts: list[str],
    ) -> tuple[list[SerpHit], list[str]]:

        weights = _provider_weights(self.cfg)

        merged: list[SerpHit] = []

        for name in chain:
            await _provider_delay(self.cfg)

            hits, err = await self._invoke(name, query, limit)

            if hits:
                merged.extend(hits)

                attempts.append(f"{name}: ok ({len(hits)})")

                ranked = _rank_hits_by_weight(merged, weights, limit)

                if len(ranked) >= limit:
                    return ranked, attempts

            else:
                attempts.append(err or f"{name}: empty")

        return _rank_hits_by_weight(merged, weights, limit), attempts

    async def _search_merge_html(
        self,
        query: str,
        limit: int,
        chain: list[str],
        attempts: list[str],
    ) -> tuple[list[SerpHit], list[str]]:
        """API 优先；HTML 引擎并行合并去重，Bing 等权重高的结果优先保留。"""

        weights = _provider_weights(self.cfg)

        merged: list[SerpHit] = []

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

        parallel = self.cfg.get("parallel_html")

        if parallel is None:
            parallel = True

        parallel = bool(parallel)

        if parallel and len(html_chain) > 1:
            tasks = [self._invoke(name, query, limit) for name in html_chain]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for name, result in zip(html_chain, results, strict=True):
                if isinstance(result, BaseException):
                    attempts.append(_format_provider_error(name, result))

                    continue

                hits, err = result

                if hits:
                    merged.extend(hits)

                    attempts.append(f"{name}: ok ({len(hits)})")

                else:
                    attempts.append(err or f"{name}: empty")

        else:
            merge_min = int(self.cfg.get("merge_min_hits") or max(3, limit // 2))

            for name in html_chain:
                await _provider_delay(self.cfg)

                hits, err = await self._invoke(name, query, limit)

                if hits:
                    merged.extend(hits)

                    attempts.append(f"{name}: ok ({len(hits)})")

                else:
                    attempts.append(err or f"{name}: empty")

                if parallel is False and len(_dedupe_hits(merged, limit * 2)) >= merge_min and len(html_chain) > 1:
                    break

        ranked = _rank_hits_by_weight(merged, weights, limit)

        return ranked, attempts

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

        if hit.meta.get("date"):
            item.personal["date"] = hit.meta["date"]

        if hit.meta.get("site"):
            item.personal["site_search"] = hit.meta["site"]

        if hit.meta.get("source_engine"):
            item.personal["searxng_source"] = hit.meta["source_engine"]

        items.append(item)

    return items
