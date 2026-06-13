"""微信公众号采集器（搜狗微信搜索）/ WeChat article collector via Sogou."""

from __future__ import annotations

import re

from osint_toolkit.collectors.base import BaseCollector
from osint_toolkit.http.client import HttpClient
from osint_toolkit.ingest.weixin_sogou import (
    search_weixin_sogou_http,
    search_weixin_sogou_playwright,
    search_weixin_sogou_serp,
    weixin_sogou_headers,
)
from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.processors.normalize import extract_text_from_html, html_to_text
from osint_toolkit.utils.config import get_weixin_config


class WeixinCollector(BaseCollector):
    name = "weixin"

    def __init__(self, client: HttpClient | None = None) -> None:
        self.client = client or HttpClient()
        self.cfg = get_weixin_config()

    async def search(self, query: str, limit: int = 10) -> list[IntelItem]:
        attempts: list[str] = []
        rows: list[dict[str, str]] = []

        http_rows, http_err = await search_weixin_sogou_http(self.client, query, limit=limit)
        if http_rows:
            rows = http_rows
            attempts.append(f"http: ok ({len(http_rows)})")
        elif http_err:
            attempts.append(http_err)

        if not rows and self.cfg.get("playwright_on_block", True):
            pw_rows, pw_err = await search_weixin_sogou_playwright(
                query,
                limit=limit,
                resolve_mp=bool(self.cfg.get("resolve_mp_urls", True)),
            )
            if pw_rows:
                rows = pw_rows
                attempts.append(f"playwright: ok ({len(pw_rows)})")
            elif pw_err:
                attempts.append(pw_err)

        if not rows and self.cfg.get("serp_fallback", True):
            serp_rows, serp_err = await search_weixin_sogou_serp(self.client, query, limit=limit)
            if serp_rows:
                rows = serp_rows
                attempts.append(f"serp: ok ({len(serp_rows)})")
            elif serp_err:
                attempts.append(serp_err)

        if not rows:
            detail = "; ".join(attempts[-4:]) if attempts else "无可用结果"
            raise RuntimeError(f"微信搜索失败: {detail}")

        items = [self._row_to_item(row) for row in rows[:limit]]
        for item in items:
            item.personal["weixin_attempts"] = attempts
        return items

    def _row_to_item(self, row: dict[str, str]) -> IntelItem:
        item = IntelItem(
            source="weixin",
            type="article",
            url=row.get("url") or row.get("sogou_url") or "",
            title=row.get("title") or "",
            content=row.get("snippet") or "",
            author=row.get("author") or "",
        )
        if row.get("sogou_url"):
            item.personal["sogou_url"] = row["sogou_url"]
        if row.get("mp_url"):
            item.personal["mp_url"] = row["mp_url"]
        if row.get("published_at"):
            item.personal["published_at"] = row["published_at"]
        if row.get("via"):
            item.personal["weixin_via"] = row["via"]
        return item

    async def fetch(self, url: str) -> IntelItem:
        target = url
        if "weixin.sogou.com" in url:
            resolved = await self._resolve_sogou_link(url)
            if resolved:
                target = resolved
        headers = weixin_sogou_headers(referer="https://weixin.sogou.com/")
        if "mp.weixin.qq.com" in target:
            headers["Referer"] = "https://mp.weixin.qq.com/"
        resp = await self.client.get(target, headers=headers)
        text = resp.text or ""
        title_match = re.search(r'var msg_title = "([^"]+)"', text)
        if not title_match:
            title_match = re.search(r"<title>(.*?)</title>", text, re.I | re.S)
        title = title_match.group(1).strip() if title_match else url
        content = extract_text_from_html(text) or html_to_text(text)
        author_match = re.search(r'var nickname = "([^"]+)"', text)
        author = author_match.group(1) if author_match else ""
        return IntelItem(
            source="weixin",
            type="article",
            url=target,
            title=title,
            content=content[:12_000],
            author=author,
        )

    async def _resolve_sogou_link(self, url: str) -> str | None:
        try:
            resp = await self.client.get(url, headers=weixin_sogou_headers(referer="https://weixin.sogou.com/"))
            final = str(resp.url)
            if "mp.weixin.qq.com" in final:
                return final
            match = re.search(r"https://mp\.weixin\.qq\.com/s\?[^\"'\s<]+", resp.text or "")
            if match:
                return match.group(0)
        except Exception:  # noqa: BLE001
            return None
        return None
