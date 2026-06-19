"""微信公众号采集器（搜狗微信搜索）/ WeChat article collector via Sogou."""

from __future__ import annotations

import asyncio
import re

from osint_toolkit.collectors.base import BaseCollector
from osint_toolkit.http.client import HttpClient
from osint_toolkit.ingest.weixin_engagement import parse_weixin_engagement
from osint_toolkit.ingest.weixin_sogou import (
    search_weixin_sogou_http,
    search_weixin_sogou_playwright,
    search_weixin_sogou_serp,
    weixin_sogou_headers,
)
from osint_toolkit.models.intel_item import IntelItem, IntelMetrics
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

        items, quality_note = await self._apply_quality_pipeline(items)
        if quality_note:
            attempts.append(quality_note)
            if items:
                items[0].personal.setdefault("collector_warnings", []).append(quality_note)

        if not items:
            return []

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

    async def _apply_quality_pipeline(self, items: list[IntelItem]) -> tuple[list[IntelItem], str]:
        """摘要预筛 → 拉取阅读量 → 按阈值剔除低质条目。"""
        notes: list[str] = []
        dropped = 0

        min_snippet = int(self.cfg.get("min_snippet_chars", 40))
        if min_snippet > 0:
            kept: list[IntelItem] = []
            for item in items:
                snippet_len = len((item.content or "").strip())
                if snippet_len < min_snippet and not item.personal.get("weixin_via") == "serp":
                    dropped += 1
                    continue
                kept.append(item)
            items = kept
            if dropped:
                notes.append(f"摘要过短剔除 {dropped} 篇")

        fetch_top = int(self.cfg.get("fetch_read_count_top", 10))
        if fetch_top > 0 and items:
            await self._enrich_read_counts(items[:fetch_top])

        min_reads = int(self.cfg.get("min_read_count", 500))
        drop_unknown = bool(self.cfg.get("drop_unknown_read_count", False))
        if min_reads > 0 or drop_unknown:
            kept = []
            read_dropped = 0
            for item in items:
                views = int(item.metrics.views or 0)
                fetched = bool(item.personal.get("weixin_read_fetched"))
                if min_reads > 0 and views > 0 and views < min_reads:
                    read_dropped += 1
                    continue
                if drop_unknown and fetched and views <= 0:
                    read_dropped += 1
                    continue
                kept.append(item)
            items = kept
            if read_dropped:
                notes.append(f"阅读量过低剔除 {read_dropped} 篇（阈值 {min_reads or '未知'}）")

        return items, "；".join(notes)

    async def _enrich_read_counts(self, items: list[IntelItem]) -> None:
        delay_ms = int(self.cfg.get("fetch_read_delay_ms", 400))
        for item in items:
            url = await self._article_url_for_item(item)
            if not url or "mp.weixin.qq.com" not in url:
                continue
            engagement = await self._fetch_engagement(url)
            item.personal["weixin_read_fetched"] = True
            if engagement["views"] > 0:
                item.metrics.views = engagement["views"]
            if engagement["likes"] > 0:
                item.metrics.likes = engagement["likes"]
            if url != item.url:
                item.url = url
                item.personal["mp_url"] = url
            if delay_ms > 0:
                await asyncio.sleep(delay_ms / 1000.0)

    async def _article_url_for_item(self, item: IntelItem) -> str | None:
        mp_url = item.personal.get("mp_url") or ""
        if mp_url and "mp.weixin.qq.com" in mp_url:
            return mp_url
        url = item.url or ""
        if "mp.weixin.qq.com" in url:
            return url
        sogou_url = item.personal.get("sogou_url") or url
        if "weixin.sogou.com" in sogou_url:
            resolved = await self._resolve_sogou_link(sogou_url)
            return resolved
        return url or None

    async def _fetch_engagement(self, url: str) -> dict[str, int]:
        headers = weixin_sogou_headers(referer="https://mp.weixin.qq.com/")
        resp = await self.client.get(url, headers=headers)
        return parse_weixin_engagement(resp.text or "")

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
        engagement = parse_weixin_engagement(text)
        return IntelItem(
            source="weixin",
            type="article",
            url=target,
            title=title,
            content=content[:12_000],
            author=author,
            metrics=IntelMetrics(
                views=engagement["views"],
                likes=engagement["likes"],
            ),
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

