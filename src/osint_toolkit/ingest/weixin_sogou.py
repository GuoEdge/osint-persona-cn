"""搜狗微信搜索 / Sogou WeChat article search."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from osint_toolkit.collectors.serp.detection import is_blocked_response
from osint_toolkit.collectors.serp.headers import serp_headers
from osint_toolkit.http.client import HttpClient

_SOUGOU_BASE = "https://weixin.sogou.com"
_ANTISPIDER_RE = re.compile(r"antispider|请输入验证码|此验证码用于确认", re.I)


def build_search_url(query: str, *, search_type: int = 2) -> str:
    """type=2 搜文章，type=1 搜公众号。"""
    return f"{_SOUGOU_BASE}/weixin?type={search_type}&query={quote(query)}&ie=utf8"


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
        author_el = li.select_one("span.all-time-y2, div.s-p span")
        rows.append(
            {
                "title": title,
                "url": _abs_link(a["href"]),
                "snippet": _clean_text(snippet_el),
                "author": _clean_text(author_el),
            }
        )
        if len(rows) >= limit:
            break
    return rows


async def search_weixin_sogou_http(
    client: HttpClient,
    query: str,
    limit: int = 10,
) -> tuple[list[dict[str, str]], str | None]:
    url = build_search_url(query)
    resp = await client.get(url, headers=serp_headers(url))
    text = resp.text or ""
    if is_weixin_blocked(text, status_code=resp.status_code, url=str(resp.url)):
        return [], "weixin_sogou: 检测到验证码/风控页面"
    rows = parse_weixin_sogou_html(text, query, limit=limit)
    if not rows and "news-list" not in text:
        return [], "weixin_sogou: 未解析到结果（页面结构可能已变更）"
    return rows, None if rows else "weixin_sogou: 空结果"


async def search_weixin_sogou_playwright(query: str, limit: int = 10) -> tuple[list[dict[str, str]], str | None]:
    """风控时通过 Playwright 打开搜狗微信搜索页并解析 DOM。"""
    from osint_toolkit.ingest.playwright_session import playwright_available, run_with_cookie_page

    if not playwright_available():
        return [], "weixin_sogou: playwright 未安装"

    search_url = build_search_url(query)

    async def _run(page: Any) -> tuple[list[dict[str, str]], str | None]:
        await page.goto(search_url, wait_until="domcontentloaded", timeout=45_000)
        await page.wait_for_timeout(1200)
        html = await page.content()
        current = page.url or ""
        if is_weixin_blocked(html, url=current):
            return [], "weixin_sogou: Playwright 仍遇到验证码"
        rows = parse_weixin_sogou_html(html, query, limit=limit)
        return rows, None if rows else "weixin_sogou: Playwright 空结果"

    rows, err = await run_with_cookie_page(_run, domains=["sogou.com", "weixin.sogou.com"])
    return rows, err
