"""知乎 recent-viewed 页 HTML 引导解析 / Bootstrap parse for browse fallback."""

from __future__ import annotations

import json
import re
from typing import Any

from osint_toolkit.http.client import HttpClient
from osint_toolkit.ingest.zhihu_activities import iter_api_data_items
from osint_toolkit.utils.zhihu_urls import content_url_from_target

_RECENT_VIEWED_URL = "https://www.zhihu.com/recent-viewed"


def _extract_embedded_state(html: str) -> dict[str, Any] | None:
    for pattern in (
        r'<script id="js-initialData"[^>]*>(.*?)</script>',
        r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
    ):
        match = re.search(pattern, html, re.S)
        if not match:
            continue
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            state = data.get("initialState") or data.get("props", {}).get("initialState") or data
            if isinstance(state, dict):
                return state
    return None


def _walk_recent_items(node: Any, out: list[dict[str, Any]], *, depth: int = 0) -> None:
    if depth > 12:
        return
    if isinstance(node, dict):
        url = content_url_from_target(node.get("target") or node, node)
        if not url:
            for key in ("url", "link", "href"):
                raw = node.get(key)
                if isinstance(raw, str) and "zhihu.com" in raw and raw.startswith("http"):
                    url = raw
                    break
        title = (
            (node.get("question") or {}).get("title")
            or node.get("title")
            or node.get("excerpt")
            or ""
        )
        if url and str(url).startswith("http") and ("question" in url or "zhuanlan" in url or "answer" in url):
            out.append(
                {
                    "source": "zhihu",
                    "title": str(title)[:200] if title else "",
                    "url": url,
                    "event_kind": "browse",
                    "via": "recent_viewed_bootstrap",
                }
            )
        for val in node.values():
            _walk_recent_items(val, out, depth=depth + 1)
    elif isinstance(node, list):
        for item in node:
            _walk_recent_items(item, out, depth=depth + 1)


def parse_recent_viewed_html(html: str, *, limit: int = 500) -> list[dict[str, Any]]:
    state = _extract_embedded_state(html)
    if not state:
        return []
    candidates: list[dict[str, Any]] = []
    for key, val in state.items():
        if any(k in key.lower() for k in ("recent", "view", "browse", "footprint", "history")):
            _walk_recent_items(val, candidates)
    if not candidates:
        _walk_recent_items(state, candidates)
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for entry in candidates:
        url = str(entry.get("url") or "")
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(entry)
        if len(out) >= limit:
            break
    return out


async def ingest_recent_viewed_bootstrap(*, limit: int = 500) -> list[dict[str, Any]]:
    client = HttpClient()
    resp = await client.get(_RECENT_VIEWED_URL)
    if resp.status_code != 200:
        return []
    return parse_recent_viewed_html(resp.text, limit=limit)


def browse_entries_from_api_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        target = item.get("target") or item
        url_ = content_url_from_target(target, item)
        if not url_ or not str(url_).startswith("http"):
            continue
        question = target.get("question") or {}
        title = question.get("title") or target.get("title") or item.get("title") or ""
        entry = {
            "source": "zhihu",
            "title": title,
            "url": url_,
            "event_kind": "browse",
            "via": "browse_api",
        }
        url = str(entry.get("url") or "")
        if url in seen:
            continue
        seen.add(url)
        out.append(entry)
    return out
