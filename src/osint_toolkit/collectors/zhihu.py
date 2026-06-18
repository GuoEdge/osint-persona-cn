"""知乎采集器 / Zhihu collector."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

from osint_toolkit.collectors.base import BaseCollector
from osint_toolkit.http.client import HttpClient
from osint_toolkit.models.intel_item import IntelItem, IntelMetrics
from osint_toolkit.processors.normalize import html_to_text
from osint_toolkit.utils.config import get_search_config
from osint_toolkit.utils.zhihu_urls import public_zhihu_url

_QUESTION_URL = re.compile(r"/question/(\d+)")
_ANSWER_URL = re.compile(r"/question/\d+/answer/(\d+)")
logger = logging.getLogger(__name__)


class ZhihuCollector(BaseCollector):
    name = "zhihu"

    def __init__(self, client: HttpClient | None = None) -> None:
        self.client = client or HttpClient()

    def _zhihu_search_cfg(self) -> dict[str, Any]:
        return dict(get_search_config())

    @staticmethod
    def question_id_from_url(url: str) -> str | None:
        if not url or "/answer/" in url:
            return None
        match = _QUESTION_URL.search(url)
        return match.group(1) if match else None

    @staticmethod
    def question_id_from_ref(url: str) -> str | None:
        match = _QUESTION_URL.search(url or "")
        return match.group(1) if match else None

    def _search_per_type_limit(self, limit: int, num_types: int) -> int:
        cfg = self._zhihu_search_cfg()
        if cfg.get("zhihu_aggressive", True):
            return int(cfg.get("zhihu_search_per_type", max(limit, 40)))
        return max(3, limit // max(1, num_types))

    @staticmethod
    def _next_search_url(paging: dict[str, Any]) -> str | None:
        if paging.get("is_end"):
            return None
        next_url = str(paging.get("next") or "").strip()
        return next_url or None

    async def _search_v3(
        self,
        query: str,
        *,
        search_type: str,
        limit: int,
        pages: int,
    ) -> list[IntelItem]:
        items: list[IntelItem] = []
        seen: set[str] = set()
        url = (
            "https://www.zhihu.com/api/v4/search_v3?"
            f"t={quote(search_type)}&q={quote(query)}&correction=1&offset=0&limit={min(limit, 20)}"
        )
        for _ in range(max(1, pages)):
            if len(items) >= limit:
                break
            resp = await self.client.get(url)
            if resp.status_code != 200:
                raise RuntimeError(f"search_v3 status={resp.status_code}")
            data = resp.json()
            for entry in data.get("data") or []:
                obj = entry.get("object", {}) or entry
                item = self._parse_object(obj)
                if not item or item.url in seen:
                    continue
                seen.add(item.url)
                items.append(item)
                if len(items) >= limit:
                    break
            next_url = self._next_search_url(data.get("paging") or {})
            if not next_url or len(items) >= limit:
                break
            url = next_url
        return items

    async def search(self, query: str, limit: int = 10) -> list[IntelItem]:
        cfg = self._zhihu_search_cfg()
        search_types = cfg.get("zhihu_search_types") or ["general", "content"]
        pages = int(cfg.get("zhihu_search_pages", 5))
        per_type = self._search_per_type_limit(limit, len(search_types))
        aggressive = bool(cfg.get("zhihu_aggressive", True))

        items: list[IntelItem] = []
        seen: set[str] = set()

        from osint_toolkit.ingest import zhihu_openapi

        openapi_cfg = zhihu_openapi.get_zhihu_config().get("openapi") or {}
        if openapi_cfg.get("prefer_search", True) and zhihu_openapi.openapi_enabled("search"):
            try:
                openapi_items = await zhihu_openapi.search(query, limit=limit, client=self.client)
                for item in openapi_items:
                    if item.url in seen:
                        continue
                    seen.add(item.url)
                    items.append(item)
            except Exception as exc:  # noqa: BLE001
                logger.debug("zhihu openapi search failed: %s", exc)

        need_more = aggressive and len(items) < per_type
        use_search_v3 = not items or (need_more and openapi_cfg.get("merge_search_v3", True))
        if use_search_v3:
            try:
                for search_type in search_types:
                    batch = await self._search_v3(
                        query,
                        search_type=str(search_type),
                        limit=per_type,
                        pages=pages,
                    )
                    for item in batch:
                        if item.url in seen:
                            continue
                        seen.add(item.url)
                        items.append(item)
            except Exception as exc:  # noqa: BLE001
                if not items:
                    items = await self._run_search_fallbacks(query, limit if not aggressive else per_type)
                    if items:
                        return items if aggressive else items[:limit]
                    raise RuntimeError(f"知乎搜索 API 不可用 ({exc})；回退也无结果") from exc

        if not items:
            items = await self._run_search_fallbacks(query, limit if not aggressive else per_type)

        expanded = await self.expand_questions(items)
        if expanded:
            for item in expanded:
                if item.url in seen:
                    continue
                seen.add(item.url)
                items.append(item)
        if aggressive:
            return items
        return items[:limit]

    async def expand_questions(self, items: list[IntelItem]) -> list[IntelItem]:
        """对搜索到的提问（及回答所属提问）批量拉取高赞回答。"""
        cfg = self._zhihu_search_cfg()
        if not cfg.get("zhihu_expand_answers", True):
            return []
        max_questions = int(cfg.get("zhihu_expand_question_top", 15))
        per_question = int(cfg.get("zhihu_answers_per_question", 50))
        expand_from_answers = bool(cfg.get("zhihu_expand_from_answers", True))

        question_meta: dict[str, tuple[str, str]] = {}
        ordered = sorted(
            [i for i in items if i.source == "zhihu"],
            key=lambda i: (0 if i.type == "question" else 1, i.url),
        )
        for item in ordered:
            qid = self.question_id_from_ref(item.url)
            if not qid or qid in question_meta:
                continue
            if "/answer/" in item.url and not expand_from_answers:
                continue
            if "/answer/" in item.url:
                qurl = f"https://www.zhihu.com/question/{qid}"
                title = str(item.personal.get("parent_question_title") or "")
            else:
                qurl = item.url if "/question/" in item.url else f"https://www.zhihu.com/question/{qid}"
                title = item.title or qurl
            question_meta[qid] = (qurl, title)
            if len(question_meta) >= max_questions:
                break

        if not question_meta:
            return []

        async def fetch_for_question(qid: str) -> list[IntelItem]:
            qurl, title = question_meta[qid]
            answers = await self.fetch_question_answers(qurl, limit=per_question)
            if answers and not title:
                title = answers[0].title or title
            for answer in answers:
                answer.personal["parent_question_url"] = qurl
                answer.personal["parent_question_title"] = title
            return answers

        batches = await asyncio.gather(
            *[fetch_for_question(qid) for qid in question_meta],
            return_exceptions=True,
        )
        expanded: list[IntelItem] = []
        for batch in batches:
            if isinstance(batch, Exception):
                continue
            expanded.extend(batch)
        return expanded

    async def fetch_question_answers(self, question_ref: str, *, limit: int = 20) -> list[IntelItem]:
        qid = self.question_id_from_ref(question_ref) or str(question_ref).strip()
        if not qid.isdigit():
            return []

        items: list[IntelItem] = []
        seen: set[str] = set()
        offset = 0
        while len(items) < limit:
            api = (
                f"https://www.zhihu.com/api/v4/questions/{qid}/answers"
                "?include=content,comment_count,voteup_count,author,question"
                f"&offset={offset}&limit=20&sort_by=vote_num"
            )
            try:
                resp = await self.client.get(api)
                if resp.status_code != 200:
                    break
                payload = resp.json()
            except Exception:  # noqa: BLE001
                break

            batch = payload.get("data") or []
            if not batch:
                break
            for obj in batch:
                if not isinstance(obj, dict):
                    continue
                item = self._parse_answer_object(obj, question_id=qid)
                if not item or item.url in seen:
                    continue
                seen.add(item.url)
                items.append(item)
                if len(items) >= limit:
                    break

            paging = payload.get("paging") or {}
            if paging.get("is_end") or not batch:
                break
            next_url = self._next_search_url(paging)
            if not next_url:
                break
            qs = parse_qs(urlparse(next_url).query)
            offset_vals = qs.get("offset") or []
            if offset_vals:
                offset = offset_vals[0]
            else:
                offset += 20
        return items

    def _parse_answer_object(self, obj: dict[str, Any], *, question_id: str | None = None) -> IntelItem | None:
        question = obj.get("question") or {}
        qid = question.get("id") or question_id
        aid = obj.get("id")
        if not aid or not qid:
            return None
        return IntelItem(
            source="zhihu",
            type="answer",
            url=f"https://www.zhihu.com/question/{qid}/answer/{aid}",
            title=question.get("title", obj.get("title", "")),
            content=html_to_text(obj.get("content", "") or obj.get("excerpt", "")),
            author=(obj.get("author") or {}).get("name", ""),
            metrics=IntelMetrics(
                likes=obj.get("voteup_count", 0),
                comments=obj.get("comment_count", 0),
            ),
        )

    async def _run_search_fallbacks(self, query: str, limit: int) -> list[IntelItem]:
        for fallback in (self._playwright_search, self._site_search, self._local_event_search):
            try:
                items = await fallback(query, limit)
            except Exception:  # noqa: BLE001
                continue
            if items:
                return items
        return []

    async def _playwright_search(self, query: str, limit: int) -> list[IntelItem]:
        """在真实浏览器上下文中调用 search_v3（自动附带 x-zse-96）。"""
        from osint_toolkit.ingest.playwright_session import playwright_available
        from osint_toolkit.ingest.zhihu_playwright import fetch_search_v3

        if not playwright_available():
            raise RuntimeError("playwright 未安装")

        data = await fetch_search_v3(query, limit=limit)
        items: list[IntelItem] = []
        for entry in (data.get("data") or [])[:limit]:
            obj = entry.get("object", {}) or entry
            item = self._parse_object(obj)
            if item:
                items.append(item)
        return items

    async def _site_search(self, query: str, limit: int) -> list[IntelItem]:
        """search_v3 被风控时，用 SERP site:zhihu.com 回退（支持多引擎轮换）。"""
        from osint_toolkit.collectors.serp.engine import SerpEngine, hits_to_items

        engine = SerpEngine(client=self.client)
        hits, _ = await engine.site_search("zhihu.com", query, limit=limit)
        items = hits_to_items(hits, source="zhihu")
        for item in items:
            href = item.url
            if "/answer/" in href:
                item.type = "answer"
            elif "/p/" in href:
                item.type = "article"
            elif "/question/" in href:
                item.type = "question"
            else:
                item.type = "snippet"
        return items

    async def _bing_site_search(self, query: str, limit: int) -> list[IntelItem]:
        return await self._site_search(query, limit)

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
            if "/answer/" in url:
                item_type = "answer"
            elif "/p/" in url:
                item_type = "article"
            elif "/question/" in url:
                item_type = "question"
            else:
                item_type = "snippet"
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

    def _parse_object(self, obj: dict) -> IntelItem | None:
        otype = obj.get("type") or obj.get("object_type", "")
        if otype == "search_result":
            obj = obj.get("object", obj)
            otype = obj.get("type", "")
        if otype == "question":
            qid = obj.get("id")
            if not qid:
                return None
            return IntelItem(
                source="zhihu",
                type="question",
                url=f"https://www.zhihu.com/question/{qid}",
                title=obj.get("title", ""),
                content=html_to_text(obj.get("excerpt", "") or obj.get("detail", "")),
                metrics=IntelMetrics(
                    likes=obj.get("voteup_count", 0),
                    comments=obj.get("comment_count", 0),
                ),
            )
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
                url=public_zhihu_url(str(obj.get("url") or ""), obj),
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
                url=public_zhihu_url(str(obj.get("url") or ""), obj),
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
        answer_match = _ANSWER_URL.search(url)
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
        qid = self.question_id_from_url(url)
        if qid:
            api = f"https://www.zhihu.com/api/v4/questions/{qid}?include=comment_count"
            try:
                resp = await self.client.get(api)
                if resp.status_code != 200:
                    return None
                data = resp.json()
                return IntelItem(
                    source="zhihu",
                    type="question",
                    url=url,
                    title=data.get("title", ""),
                    content=html_to_text(data.get("detail", "") or data.get("excerpt", "")),
                    metrics=IntelMetrics(
                        likes=data.get("voteup_count", 0),
                        comments=data.get("comment_count", 0),
                    ),
                )
            except Exception:  # noqa: BLE001
                return None
        return None

    def _comment_resource(self, url: str) -> tuple[str, str] | None:
        answer_match = _ANSWER_URL.search(url)
        if answer_match:
            return "answers", answer_match.group(1)
        article_match = re.search(r"(?:zhuanlan\.zhihu\.com)?/p/(\d+)", url)
        if article_match:
            return "articles", article_match.group(1)
        return None

    def _comment_limits(self) -> tuple[int, int]:
        cfg = self._zhihu_search_cfg()
        limit = int(cfg.get("zhihu_comment_limit", 120))
        pages = int(cfg.get("zhihu_comment_pages", 8))
        return limit, pages

    async def _fetch_child_comments(
        self,
        kind: str,
        rid: str,
        root_id: str,
        *,
        limit: int,
    ) -> list[dict]:
        collected: list[dict] = []
        offset = ""
        pages = 0
        while len(collected) < limit and pages < 3:
            api = (
                f"https://www.zhihu.com/api/v4/comment_v5/{kind}/{rid}/root_comment/{root_id}/child_comment"
                f"?limit=20&order_by=score"
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
        return collected[:limit]

    async def fetch_comments(self, url: str, limit: int | None = None) -> list[dict]:
        resource = self._comment_resource(url)
        if not resource:
            return []
        cfg = self._zhihu_search_cfg()
        cfg_limit, max_pages = self._comment_limits()
        target_limit = limit if limit is not None else cfg_limit
        kind, rid = resource
        collected: list[dict] = []
        offset = ""
        pages = 0
        while len(collected) < target_limit and pages < max_pages:
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
                        "child_count": entry.get("child_comment_count", 0),
                    }
                )
                if len(collected) >= target_limit:
                    break
            paging = data.get("paging") or {}
            if paging.get("is_end") or not paging.get("next"):
                break
            offset = str(paging.get("next") or "")
            pages += 1
        collected.sort(key=lambda c: c.get("likes", 0), reverse=True)
        collected = collected[:target_limit]

        if cfg.get("zhihu_fetch_child_comments", True):
            roots = int(cfg.get("zhihu_child_comment_roots", 10))
            child_limit = int(cfg.get("zhihu_child_comment_limit", 20))
            child_tasks = []
            targets: list[dict] = []
            for entry in collected[:roots]:
                child_id = entry.get("id")
                if not child_id or not entry.get("child_count"):
                    continue
                targets.append(entry)
                child_tasks.append(
                    self._fetch_child_comments(kind, rid, str(child_id), limit=child_limit)
                )
            if child_tasks:
                child_batches = await asyncio.gather(*child_tasks, return_exceptions=True)
                for entry, batch in zip(targets, child_batches, strict=False):
                    if isinstance(batch, list) and batch:
                        entry["replies"] = batch
        return collected
