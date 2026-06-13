"""SERP 提供方 / Search engine providers."""

from __future__ import annotations

import asyncio
import os
from typing import Any
from urllib.parse import quote

from bs4 import BeautifulSoup

from osint_toolkit.collectors.serp.detection import is_blocked_response
from osint_toolkit.collectors.serp.headers import serp_headers
from osint_toolkit.collectors.serp.models import SerpHit
from osint_toolkit.collectors.serp.urls import normalize_result_url
from osint_toolkit.http.client import HttpClient

HTML_PROVIDERS = frozenset(
    {"bing_html", "baidu_html", "duckduckgo_html", "sogou_html"},
)
API_PROVIDERS = frozenset({"bing_api", "serpapi", "serpapi_baidu", "searxng"})


def _resolve_key(cfg: dict, key_name: str, env_name: str) -> str:
    val = str(cfg.get(key_name) or os.environ.get(env_name) or "").strip()
    return val


def _html_ua(cfg: dict) -> str | None:
    ua = str(cfg.get("html_user_agent") or "").strip()
    return ua or None


def _hit(
    *,
    title: str,
    url: str,
    snippet: str,
    engine: str,
    query: str,
    meta: dict[str, Any] | None = None,
) -> SerpHit | None:
    normalized = normalize_result_url(url)
    if not normalized or not normalized.startswith("http"):
        return None
    title = title.strip()
    if not title:
        return None
    return SerpHit(
        title=title,
        url=normalized,
        snippet=snippet.strip(),
        engine=engine,
        query=query,
        meta=meta or {},
    )


async def _get_html(client: HttpClient, url: str, cfg: dict) -> tuple[str, int]:
    resp = await client.get(url, headers=serp_headers(url, user_agent=_html_ua(cfg)))
    return resp.text or "", resp.status_code


async def search_bing_html(client: HttpClient, query: str, limit: int, cfg: dict | None = None) -> tuple[list[SerpHit], str | None]:
    cfg = cfg or {}
    url = f"https://www.bing.com/search?q={quote(query)}&setlang=zh-Hans&ensearch=0"
    text, status = await _get_html(client, url, cfg)
    if is_blocked_response(text, status_code=status):
        return [], "bing_html: 检测到 CAPTCHA/风控页面"
    soup = BeautifulSoup(text, "html.parser")
    hits: list[SerpHit] = []
    blocks = soup.select("li.b_algo, li.b_ans, #b_results > .b_algo")
    for li in blocks[: limit * 2]:
        a = li.select_one("h2 a, a[href^='http']")
        if not a or not a.get("href"):
            continue
        snippet_el = li.select_one("p, .b_caption p, .b_lineclamp2, .b_lineclamp3")
        hit = _hit(
            title=a.get_text(strip=True),
            url=a["href"],
            snippet=snippet_el.get_text(strip=True) if snippet_el else "",
            engine="bing_html",
            query=query,
        )
        if hit:
            hits.append(hit)
        if len(hits) >= limit:
            break
    if not hits and "b_algo" not in text and "b_results" not in text:
        return [], "bing_html: 未解析到结果（可能页面结构已变更）"
    return hits, None if hits else "bing_html: 空结果"


async def search_baidu_html(client: HttpClient, query: str, limit: int, cfg: dict | None = None) -> tuple[list[SerpHit], str | None]:
    cfg = cfg or {}
    url = f"https://www.baidu.com/s?wd={quote(query)}&rn={min(limit, 50)}&ie=utf-8"
    text, status = await _get_html(client, url, cfg)
    if is_blocked_response(text, status_code=status):
        return [], "baidu_html: 检测到验证码/风控页面"
    soup = BeautifulSoup(text, "html.parser")
    hits: list[SerpHit] = []
    containers = soup.select("#content_left .result, #content_left .c-container, .result-op")
    for block in containers[: limit * 2]:
        a = block.select_one("h3 a, a[href^='http']")
        if not a or not a.get("href"):
            continue
        snippet_el = block.select_one(".c-abstract, .content-right_8Zs40, .c-span-last, .c-font-normal")
        hit = _hit(
            title=a.get_text(strip=True),
            url=a["href"],
            snippet=snippet_el.get_text(strip=True) if snippet_el else "",
            engine="baidu_html",
            query=query,
        )
        if hit:
            hits.append(hit)
        if len(hits) >= limit:
            break
    return hits, None if hits else "baidu_html: 空结果"


async def search_duckduckgo_html(client: HttpClient, query: str, limit: int, cfg: dict | None = None) -> tuple[list[SerpHit], str | None]:
    cfg = cfg or {}
    region = str(cfg.get("duckduckgo_region") or "cn-zh").strip()
    url = f"https://html.duckduckgo.com/html/?q={quote(query)}&kl={quote(region)}"
    text, status = await _get_html(client, url, cfg)
    if is_blocked_response(text, status_code=status):
        return [], "duckduckgo_html: 检测到阻断页面"
    soup = BeautifulSoup(text, "html.parser")
    hits: list[SerpHit] = []
    blocks = soup.select("div.result, div.web-result, table.result")
    for block in blocks[: limit * 2]:
        a = block.select_one("a.result__a, a.result-link, h2 a")
        if not a or not a.get("href"):
            continue
        snippet_el = block.select_one("a.result__snippet, div.result__snippet, td.result__snippet")
        hit = _hit(
            title=a.get_text(strip=True),
            url=a["href"],
            snippet=snippet_el.get_text(strip=True) if snippet_el else "",
            engine="duckduckgo_html",
            query=query,
        )
        if hit:
            hits.append(hit)
        if len(hits) >= limit:
            break
    return hits, None if hits else "duckduckgo_html: 空结果"


async def search_sogou_html(client: HttpClient, query: str, limit: int, cfg: dict | None = None) -> tuple[list[SerpHit], str | None]:
    cfg = cfg or {}
    url = f"https://www.sogou.com/web?query={quote(query)}&num={min(limit, 20)}"
    text, status = await _get_html(client, url, cfg)
    if is_blocked_response(text, status_code=status):
        return [], "sogou_html: 检测到验证码/风控页面"
    soup = BeautifulSoup(text, "html.parser")
    hits: list[SerpHit] = []
    blocks = soup.select("div.vrwrap, div.rb, div.results div.result")
    for block in blocks[: limit * 2]:
        a = block.select_one("h3 a, h4 a, a[data-share-url]")
        if not a or not a.get("href"):
            continue
        snippet_el = block.select_one("p.str-info, p.str-text, .str-info, .space-txt")
        hit = _hit(
            title=a.get_text(strip=True),
            url=a["href"],
            snippet=snippet_el.get_text(strip=True) if snippet_el else "",
            engine="sogou_html",
            query=query,
        )
        if hit:
            hits.append(hit)
        if len(hits) >= limit:
            break
    return hits, None if hits else "sogou_html: 空结果"


async def search_bing_api(client: HttpClient, query: str, limit: int, cfg: dict) -> tuple[list[SerpHit], str | None]:
    key = _resolve_key(cfg, "bing_api_key", "BING_SEARCH_API_KEY")
    if not key:
        return [], "bing_api: 未配置 BING_SEARCH_API_KEY"
    url = f"https://api.bing.microsoft.com/v7.0/search?q={quote(query)}&count={limit}&mkt=zh-CN"
    resp = await client.get(url, headers={"Ocp-Apim-Subscription-Key": key})
    if resp.status_code != 200:
        return [], f"bing_api: HTTP {resp.status_code}"
    data = resp.json()
    hits: list[SerpHit] = []
    for entry in (data.get("webPages") or {}).get("value") or []:
        hit = _hit(
            title=str(entry.get("name") or ""),
            url=str(entry.get("url") or ""),
            snippet=str(entry.get("snippet") or ""),
            engine="bing_api",
            query=query,
            meta={"date": entry.get("dateLastCrawled")},
        )
        if hit:
            hits.append(hit)
    return hits[:limit], None if hits else "bing_api: 空结果"


async def _search_serpapi_engine(
    client: HttpClient,
    query: str,
    limit: int,
    cfg: dict,
    *,
    engine: str,
    label: str,
) -> tuple[list[SerpHit], str | None]:
    key = _resolve_key(cfg, "serpapi_key", "SERPAPI_KEY")
    if not key:
        return [], f"{label}: 未配置 SERPAPI_KEY"
    url = (
        f"https://serpapi.com/search.json?engine={quote(engine)}&q={quote(query)}"
        f"&num={limit}&api_key={quote(key)}"
    )
    resp = await client.get(url)
    if resp.status_code != 200:
        return [], f"{label}: HTTP {resp.status_code}"
    data = resp.json()
    if data.get("error"):
        return [], f"{label}: {data.get('error')}"
    hits: list[SerpHit] = []
    for entry in data.get("organic_results") or []:
        hit = _hit(
            title=str(entry.get("title") or ""),
            url=str(entry.get("link") or ""),
            snippet=str(entry.get("snippet") or ""),
            engine=label,
            query=query,
        )
        if hit:
            hits.append(hit)
    return hits[:limit], None if hits else f"{label}: 空结果"


async def search_serpapi(client: HttpClient, query: str, limit: int, cfg: dict) -> tuple[list[SerpHit], str | None]:
    return await _search_serpapi_engine(client, query, limit, cfg, engine="bing", label="serpapi")


async def search_serpapi_baidu(client: HttpClient, query: str, limit: int, cfg: dict) -> tuple[list[SerpHit], str | None]:
    return await _search_serpapi_engine(client, query, limit, cfg, engine="baidu", label="serpapi_baidu")


async def search_searxng(client: HttpClient, query: str, limit: int, cfg: dict) -> tuple[list[SerpHit], str | None]:
    base = _resolve_key(cfg, "searxng_base_url", "SEARXNG_BASE_URL")
    if not base:
        return [], "searxng: 未配置 SEARXNG_BASE_URL"
    base = base.rstrip("/")
    url = f"{base}/search?q={quote(query)}&format=json&language=zh-CN"
    resp = await client.get(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": serp_headers(url).get("User-Agent", ""),
        },
    )
    if resp.status_code == 403:
        return [], "searxng: 403（实例可能未启用 format=json）"
    if resp.status_code != 200:
        return [], f"searxng: HTTP {resp.status_code}"
    try:
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return [], f"searxng: 非 JSON 响应 ({exc})"
    hits: list[SerpHit] = []
    for entry in data.get("results") or []:
        hit = _hit(
            title=str(entry.get("title") or ""),
            url=str(entry.get("url") or ""),
            snippet=str(entry.get("content") or entry.get("snippet") or ""),
            engine="searxng",
            query=query,
            meta={"source_engine": entry.get("engine")},
        )
        if hit:
            hits.append(hit)
        if len(hits) >= limit:
            break
    return hits, None if hits else "searxng: 空结果"


async def _provider_delay(cfg: dict) -> None:
    delay_ms = int(cfg.get("provider_delay_ms") or 0)
    if delay_ms > 0:
        await asyncio.sleep(delay_ms / 1000.0)


PROVIDERS = {
    "bing_html": search_bing_html,
    "baidu_html": search_baidu_html,
    "duckduckgo_html": search_duckduckgo_html,
    "sogou_html": search_sogou_html,
    "bing_api": search_bing_api,
    "serpapi": search_serpapi,
    "serpapi_baidu": search_serpapi_baidu,
    "searxng": search_searxng,
}
