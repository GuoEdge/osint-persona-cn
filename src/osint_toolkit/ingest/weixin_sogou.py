"""搜狗微信搜索 / Sogou WeChat article search."""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from http.cookies import SimpleCookie
from typing import Any
from urllib.parse import quote, urljoin

import httpx
from bs4 import BeautifulSoup

from osint_toolkit.auth.cookie_sync import cookie_header_for_url
from osint_toolkit.collectors.serp.detection import is_blocked_response
from osint_toolkit.http.client import HttpClient
from osint_toolkit.utils.config import get_weixin_config

_SOUGOU_BASE = "https://weixin.sogou.com"
_ANTISPIDER_RE = re.compile(r"antispider|请输入验证码|此验证码用于确认", re.I)
_TIME_RE = re.compile(r"timeConvert\(['\"](\d+)['\"]\)")


def build_search_url(query: str, *, search_type: int = 2) -> str:
    """type=2 搜文章，type=1 搜公众号。"""
    return f"{_SOUGOU_BASE}/weixin?type={search_type}&query={quote(query)}&ie=utf8"


def weixin_sogou_headers(*, referer: str | None = None, user_agent: str | None = None) -> dict[str, str]:
    ua = user_agent or (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"
    )
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    headers["Referer"] = referer or f"{_SOUGOU_BASE}/"
    cookie = cookie_header_for_url(_SOUGOU_BASE)
    if cookie:
        headers["Cookie"] = cookie
    return headers


def is_weixin_blocked(text: str, *, status_code: int = 200, url: str = "") -> bool:
    if "antispider" in (url or "").lower():
        return True
    if _ANTISPIDER_RE.search(text[:12_000]):
        return True
    return is_blocked_response(text, status_code=status_code)


def _clean_text(node: Any) -> str:
    if node is None:
        return ""
    for em in node.find_all("em"):
        em.unwrap()
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()


def _abs_link(href: str) -> str:
    href = (href or "").strip()
    if not href:
        return ""
    if href.startswith("http"):
        return href
    return urljoin(_SOUGOU_BASE, href)


def _format_ts(raw: str) -> str:
    try:
        ts = int(raw)
        if ts > 1_000_000_000_000:
            ts //= 1000
        return datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return ""


def _extract_published(li: Any) -> str:
    scripts = " ".join(script.get_text(" ", strip=True) for script in li.find_all("script"))
    match = _TIME_RE.search(scripts)
    if match:
        return _format_ts(match.group(1))
    for span in li.select("span.s2, span.s3"):
        text = span.get_text(strip=True)
        if text and not text.isdigit():
            return text
    return ""


def parse_weixin_sogou_html(html: str, query: str, limit: int = 10) -> list[dict[str, str]]:
    """解析搜狗微信搜索结果页。"""
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, str]] = []
    for li in soup.select("ul.news-list > li")[: limit * 2]:
        a = li.select_one("h3 a")
        if not a or not a.get("href"):
            continue
        title = _clean_text(a)
        if not title:
            continue
        snippet_el = li.select_one("p.txt-info, p")
        author_el = li.select_one("span.all-time-y2, div.s-p span.all-time-y2")
        sogou_url = _abs_link(a["href"])
        row = {
            "title": title,
            "url": sogou_url,
            "sogou_url": sogou_url,
            "snippet": _clean_text(snippet_el),
            "author": _clean_text(author_el),
            "published_at": _extract_published(li),
            "query": query,
        }
        rows.append(row)
        if len(rows) >= limit:
            break
    return rows


def _apply_synced_cookies(client: httpx.AsyncClient, url: str) -> None:
    header = cookie_header_for_url(url)
    if not header:
        return
    jar = SimpleCookie()
    jar.load(header)
    for name, morsel in jar.items():
        client.cookies.set(name, morsel.value, domain=".sogou.com")


class WeixinSogouSession:
    """带 Cookie 预热与跳转链的搜狗微信 HTTP 会话。"""

    def __init__(self, http: HttpClient | None = None) -> None:
        self.http = http or HttpClient()
        self._client: httpx.AsyncClient | None = None
        self.search_url = ""

    async def __aenter__(self) -> WeixinSogouSession:
        self._client = httpx.AsyncClient(
            timeout=self.http.timeout,
            proxy=self.http._proxy,
            follow_redirects=True,
            trust_env=False,
            headers=weixin_sogou_headers(user_agent=self.http.user_agent),
        )
        _apply_synced_cookies(self._client, _SOUGOU_BASE)
        await self._client.get(f"{_SOUGOU_BASE}/")
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def search(self, query: str, limit: int = 10) -> tuple[list[dict[str, str]], str | None]:
        if not self._client:
            raise RuntimeError("WeixinSogouSession 未初始化")
        self.search_url = build_search_url(query)
        headers = weixin_sogou_headers(referer=f"{_SOUGOU_BASE}/", user_agent=self.http.user_agent)
        cookie = cookie_header_for_url(_SOUGOU_BASE)
        if cookie:
            headers["Cookie"] = cookie
        resp = await self._client.get(self.search_url, headers=headers)
        text = resp.text or ""
        if is_weixin_blocked(text, status_code=resp.status_code, url=str(resp.url)):
            return [], "weixin_sogou: 检测到验证码/风控页面"
        rows = parse_weixin_sogou_html(text, query, limit=limit)
        if not rows and "news-list" not in text:
            return [], "weixin_sogou: 未解析到结果（页面结构可能已变更）"
        if rows:
            await self._resolve_mp_urls(rows, limit=min(3, len(rows)))
        return rows, None if rows else "weixin_sogou: 空结果"

    async def _resolve_mp_urls(self, rows: list[dict[str, str]], limit: int) -> None:
        if not self._client or not self.search_url:
            return
        referer = self.search_url
        for row in rows[:limit]:
            sogou_url = row.get("sogou_url") or row.get("url") or ""
            if not sogou_url or "weixin.sogou.com" not in sogou_url:
                continue
            try:
                headers = weixin_sogou_headers(referer=referer, user_agent=self.http.user_agent)
                resp = await self._client.get(sogou_url, headers=headers)
                final = str(resp.url)
                if "mp.weixin.qq.com" in final:
                    row["mp_url"] = final
                    row["url"] = final
                    continue
                match = re.search(r"https://mp\.weixin\.qq\.com/s\?[^\"'\s<]+", resp.text or "")
                if match:
                    row["mp_url"] = match.group(0)
                    row["url"] = match.group(0)
            except Exception:  # noqa: BLE001
                continue
            await asyncio.sleep(0.35)


async def search_weixin_sogou_http(
    client: HttpClient | None,
    query: str,
    limit: int = 10,
) -> tuple[list[dict[str, str]], str | None]:
    async with WeixinSogouSession(client) as session:
        return await session.search(query, limit=limit)


async def search_weixin_sogou_playwright(
    query: str,
    limit: int = 10,
    *,
    resolve_mp: bool = True,
) -> tuple[list[dict[str, str]], str | None]:
    """风控时通过 Playwright 打开搜狗微信搜索页并解析 DOM。"""
    from osint_toolkit.ingest.playwright_session import playwright_available, run_with_cookie_page

    if not playwright_available():
        return [], "weixin_sogou: playwright 未安装"

    search_url = build_search_url(query)
    cfg = get_weixin_config()
    resolve_top = int(cfg.get("resolve_top") or 3) if resolve_mp else 0

    async def _run(page: Any) -> tuple[list[dict[str, str]], str | None]:
        await page.goto(f"{_SOUGOU_BASE}/", wait_until="domcontentloaded", timeout=45_000)
        await page.wait_for_timeout(600)
        await page.goto(search_url, wait_until="domcontentloaded", timeout=45_000)
        try:
            await page.wait_for_selector("ul.news-list li", timeout=12_000)
        except Exception:  # noqa: BLE001
            pass
        html = await page.content()
        current = page.url or ""
        if is_weixin_blocked(html, url=current):
            return [], "weixin_sogou: Playwright 仍遇到验证码"
        rows = parse_weixin_sogou_html(html, query, limit=limit)
        if rows and resolve_top > 0:
            for row in rows[:resolve_top]:
                sogou_url = row.get("sogou_url") or row.get("url") or ""
                if not sogou_url:
                    continue
                try:
                    await page.goto(sogou_url, wait_until="domcontentloaded", timeout=30_000, referer=search_url)
                    await page.wait_for_timeout(500)
                    final = page.url or ""
                    if "mp.weixin.qq.com" in final:
                        row["mp_url"] = final
                        row["url"] = final
                except Exception:  # noqa: BLE001
                    continue
        return rows, None if rows else "weixin_sogou: Playwright 空结果"

    return await run_with_cookie_page(_run, domains=["sogou.com", "weixin.sogou.com"])


async def search_weixin_sogou_serp(
    client: HttpClient | None,
    query: str,
    limit: int = 10,
) -> tuple[list[dict[str, str]], str | None]:
    """搜狗失败时，用通用 SERP site:mp.weixin.qq.com 兜底。"""
    from osint_toolkit.collectors.serp.engine import SerpEngine

    engine = SerpEngine(client=client)
    hits, attempts = await engine.site_search("mp.weixin.qq.com", query, limit=limit)
    if not hits:
        tail = "; ".join(attempts[-2:]) if attempts else "无结果"
        return [], f"weixin_serp: {tail}"
    rows: list[dict[str, str]] = []
    for hit in hits:
        rows.append(
            {
                "title": hit.title,
                "url": hit.url,
                "snippet": hit.snippet,
                "author": "",
                "published_at": "",
                "query": query,
                "via": "serp",
            }
        )
    return rows, None
