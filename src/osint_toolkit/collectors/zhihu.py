"""知乎采集器 / Zhihu collector."""

from __future__ import annotations

import re
from urllib.parse import quote

from bs4 import BeautifulSoup

from osint_toolkit.collectors.base import BaseCollector
from osint_toolkit.http.client import HttpClient
from osint_toolkit.models.intel_item import IntelItem, IntelMetrics
from osint_toolkit.processors.normalize import html_to_text


class ZhihuCollector(BaseCollector):
    name = "zhihu"

    def __init__(self, client: HttpClient | None = None) -> None:
        self.client = client or HttpClient()

    async def search(self, query: str, limit: int = 10) -> list[IntelItem]:
        api = (
            "https://www.zhihu.com/api/v4/search_v3?"
            f"t=general&q={quote(query)}&correction=1&offset=0&limit={limit}"
        )
        items: list[IntelItem] = []
        try:
            resp = await self.client.get(api)
            if resp.status_code != 200:
                raise RuntimeError(f"search_v3 status={resp.status_code}")
            data = resp.json()
            for entry in (data.get("data") or [])[:limit]:
                obj = entry.get("object", {}) or entry
                item = self._parse_object(obj)
                if item:
                    items.append(item)
        except Exception as exc:  # noqa: BLE001
            for fallback in (self._bing_site_search, self._local_event_search):
                items = await fallback(query, limit)
                if items:
                    return items[:limit]
            raise RuntimeError(f"知乎搜索 API 不可用 ({exc})；回退也无结果") from exc
        if not items:
            for fallback in (self._bing_site_search, self._local_event_search):
                items = await fallback(query, limit)
                if items:
                    break
        return items[:limit]

    async def _bing_site_search(self, query: str, limit: int) -> list[IntelItem]:
        """search_v3 被风控时，用 Bing site:zhihu.com 回退。"""
        url = f"https://www.bing.com/search?q={quote(f'site:zhihu.com {query}')}&setlang=zh-Hans"
        items: list[IntelItem] = []
        try:
            html = await self.client.get_text(url)
            soup = BeautifulSoup(html, "html.parser")
            seen: set[str] = set()
            for li in soup.select("li.b_algo"):
                a = li.find("a")
                if not a or not a.get("href"):
                    continue
                href = a["href"]
                if "zhihu.com" not in href or href in seen:
                    continue
                seen.add(href)
                title = a.get_text(strip=True)
                snippet = ""
                p = li.find("p")
                if p:
                    snippet = p.get_text(strip=True)
                item_type = "answer" if "/answer/" in href else "article" if "/p/" in href else "snippet"
                items.append(
                    IntelItem(
                        source="zhihu",
                        type=item_type,
                        url=href,
                        title=title,
                        content=snippet,
                    )
                )
                if len(items) >= limit:
                    break
        except Exception:  # noqa: BLE001
            return []
        return items

    async def _local_event_search(self, query: str, limit: int) -> list[IntelItem]:
        """从本地 events 库匹配知乎历史行为（Cookie API 搜索被拒时的实用回退）。"""
        import json

        from osint_toolkit.storage.sqlite import connect

        tokens = [t for t in re.split(r"\s+", query.strip()) if len(t) >= 2]
        conn = connect()
        rows = conn.execute(
            """
            SELECT data_json FROM events
            WHERE event_type IN ('zhihu_fav', 'zhihu_vote', 'zhihu_browse', 'zhihu_activity')
               OR (event_type LIKE 'zhihu_%' AND json_extract(data_json, '$.url') LIKE '%zhihu.com%')
            ORDER BY id DESC
            LIMIT 1200
            """
        ).fetchall()
        conn.close()

        def to_item(data: dict) -> IntelItem | None:
            url = str(data.get("url") or "")
            if not url or "zhihu.com/people/" in url:
                return None
            if not any(x in url for x in ("/answer/", "/p/", "/question/", "zhuanlan")):
                return None
            title = str(data.get("title") or url)
            item_type = "answer" if "/answer/" in url else "article" if "/p/" in url else "snippet"
            return IntelItem(
                source="zhihu",
                type=item_type,
                url=url,
                title=title,
                content=str(data.get("content") or data.get("folder") or ""),
            )

        matched: list[IntelItem] = []
        recent_pool: list[IntelItem] = []
        seen: set[str] = set()
        for row in rows:
            data = json.loads(row["data_json"])
            item = to_item(data)
            if not item or item.url in seen:
                continue
            seen.add(item.url)
            recent_pool.append(item)
            if tokens:
                hay = f"{item.title} {item.url}".lower()
                if any(tok.lower() in hay for tok in tokens):
                    matched.append(item)
            if len(matched) >= limit:
                break
        if matched:
            return matched[:limit]
        return recent_pool[:limit]

    async def _fallback_search(self, query: str, limit: int) -> list[IntelItem]:
        for fallback in (self._bing_site_search, self._local_event_search):
            items = await fallback(query, limit)
            if items:
                return items
        raise RuntimeError("知乎搜索失败：API 与回退均无结果")

    def _parse_object(self, obj: dict) -> IntelItem | None:
        otype = obj.get("type") or obj.get("object_type", "")
        if otype == "search_result":
            obj = obj.get("object", obj)
            otype = obj.get("type", "")
        if otype == "answer":
            question = obj.get("question", {})
            return IntelItem(
                source="zhihu",
                type="answer",
                url=f"https://www.zhihu.com/question/{question.get('id')}/answer/{obj.get('id')}",
                title=question.get("title", obj.get("title", "")),
                content=html_to_text(obj.get("excerpt", "") or obj.get("content", "")),
                author=obj.get("author", {}).get("name", ""),
                metrics=IntelMetrics(
                    likes=obj.get("voteup_count", 0),
                    comments=obj.get("comment_count", 0),
                ),
            )
        if otype in {"article", "zvideo"}:
            return IntelItem(
                source="zhihu",
                type=otype,
                url=obj.get("url", ""),
                title=obj.get("title", ""),
                content=html_to_text(obj.get("excerpt", "") or ""),
                author=obj.get("author", {}).get("name", ""),
                metrics=IntelMetrics(likes=obj.get("voteup_count", 0)),
            )
        title = obj.get("title") or obj.get("question", {}).get("title")
        if title:
            return IntelItem(
                source="zhihu",
                type="content",
                url=obj.get("url", ""),
                title=title,
                content=html_to_text(obj.get("excerpt", "") or ""),
            )
        return None

    async def fetch(self, url: str) -> IntelItem:
        item = await self._fetch_via_api(url)
        if item:
            return item
        text = await self.client.get_text(url)
        title_match = re.search(r"<title>(.*?)</title>", text, re.I | re.S)
        title = title_match.group(1).strip() if title_match else url
        content = html_to_text(text)
        return IntelItem(
            source="zhihu",
            type="page",
            url=url,
            title=title,
            content=content[:8000],
        )

    async def _fetch_via_api(self, url: str) -> IntelItem | None:
        answer_match = re.search(r"/question/\d+/answer/(\d+)", url)
        if answer_match:
            aid = answer_match.group(1)
            api = f"https://www.zhihu.com/api/v4/answers/{aid}?include=content,question"
            try:
                resp = await self.client.get(api)
                if resp.status_code != 200:
                    return None
                data = resp.json()
                question = data.get("question") or {}
                return IntelItem(
                    source="zhihu",
                    type="answer",
                    url=url,
                    title=question.get("title", data.get("title", "")),
                    content=html_to_text(data.get("content", "") or data.get("excerpt", "")),
                    author=(data.get("author") or {}).get("name", ""),
                    metrics=IntelMetrics(
                        likes=data.get("voteup_count", 0),
                        comments=data.get("comment_count", 0),
                    ),
                )
            except Exception:  # noqa: BLE001
                return None
        article_match = re.search(r"(?:zhuanlan\.zhihu\.com)?/p/(\d+)", url)
        if article_match:
            pid = article_match.group(1)
            api = f"https://www.zhihu.com/api/v4/articles/{pid}"
            try:
                resp = await self.client.get(api)
                if resp.status_code != 200:
                    return None
                data = resp.json()
                return IntelItem(
                    source="zhihu",
                    type="article",
                    url=url,
                    title=data.get("title", ""),
                    content=html_to_text(data.get("content", "") or data.get("excerpt", "")),
                    author=(data.get("author") or {}).get("name", ""),
                    metrics=IntelMetrics(
                        likes=data.get("voteup_count", 0),
                        comments=data.get("comment_count", 0),
                    ),
                )
            except Exception:  # noqa: BLE001
                return None
        return None

    def _comment_resource(self, url: str) -> tuple[str, str] | None:
        answer_match = re.search(r"/question/\d+/answer/(\d+)", url)
        if answer_match:
            return "answers", answer_match.group(1)
        article_match = re.search(r"(?:zhuanlan\.zhihu\.com)?/p/(\d+)", url)
        if article_match:
            return "articles", article_match.group(1)
        return None

    async def fetch_comments(self, url: str, limit: int = 40) -> list[dict]:
        resource = self._comment_resource(url)
        if not resource:
            return []
        kind, rid = resource
        collected: list[dict] = []
        offset = ""
        pages = 0
        while len(collected) < limit and pages < 2:
            api = (
                f"https://www.zhihu.com/api/v4/comment_v5/{kind}/{rid}/root_comment"
                f"?order_by=score&limit=20"
            )
            if offset:
                api += f"&offset={quote(offset)}"
            try:
                resp = await self.client.get(api)
                if resp.status_code != 200:
                    break
                data = resp.json()
            except Exception:  # noqa: BLE001
                break
            for entry in data.get("data") or []:
                collected.append(
                    {
                        "author": (entry.get("author") or {}).get("name", ""),
                        "content": html_to_text(entry.get("content", "")),
                        "likes": entry.get("vote_count", 0),
                        "id": entry.get("id"),
                    }
                )
                if len(collected) >= limit:
                    break
            paging = data.get("paging") or {}
            if paging.get("is_end") or not paging.get("next"):
                break
            offset = str(paging.get("next") or "")
            pages += 1
        collected.sort(key=lambda c: c.get("likes", 0), reverse=True)
        return collected[:limit]
