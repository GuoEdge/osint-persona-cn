"""收录服务 / Save service."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from osint_toolkit.analyzers.comments import summarize_comments
from osint_toolkit.auth.paths import get_data_dir
from osint_toolkit.collectors.bilibili import BilibiliCollector
from osint_toolkit.collectors.web import WebCollector
from osint_toolkit.collectors.weixin import WeixinCollector
from osint_toolkit.collectors.zhihu import ZhihuCollector
from osint_toolkit.exporters.card import export_card
from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.services.run_session import run_dir_for_read
from osint_toolkit.storage.knowledge import save_item


def _load_run_dedup_items(run_id: str) -> list[IntelItem]:
    run_dir = run_dir_for_read(run_id)
    if not run_dir.exists():
        raise FileNotFoundError(f"run not found: {run_id}")
    for path in sorted(run_dir.glob("*items_dedup.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        items_raw = raw if isinstance(raw, list) else raw.get("items") or []
        return [IntelItem.from_dict(d) for d in items_raw if isinstance(d, dict)]
    raise FileNotFoundError(f"items_dedup not found for run: {run_id}")


def save_run_items(
    run_id: str,
    *,
    item_ids: list[str] | None = None,
    min_relevance: float = 0.25,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """从 run 目录批量收录去重后的条目到知识库。"""
    items = _load_run_dedup_items(run_id)
    id_set = set(item_ids) if item_ids else None
    saved_ids: list[str] = []
    for item in items:
        if id_set is not None and item.id not in id_set:
            continue
        rel = float(getattr(getattr(item, "signals", None), "relevance", 0) or 0)
        if rel < min_relevance:
            continue
        if getattr(getattr(item, "signals", None), "fold_reason", None):
            continue
        item.personal["run_id"] = run_id
        if tags:
            item.personal["tags"] = list(tags)
        save_item(item)
        saved_ids.append(item.id)
    return {"run_id": run_id, "saved_count": len(saved_ids), "saved_ids": saved_ids}


async def save_url(
    url: str,
    *,
    with_comments: bool = False,
    no_ai: bool = False,
) -> dict[str, Any]:
    from osint_toolkit.http.ssrf import SSRFError, assert_public_http_url

    try:
        assert_public_http_url(url)
    except SSRFError as exc:
        raise ValueError(str(exc)) from exc
    host = urlparse(url).hostname or ""
    if "zhihu.com" in host:
        collector = ZhihuCollector()
        item = await collector.fetch(url)
        if with_comments:
            comments = await collector.fetch_comments(url)
            item.layers["comments"] = comments
            item.layers["comments_summary"] = await summarize_comments(comments, no_ai=no_ai)
    elif "mp.weixin.qq.com" in host or "weixin.sogou.com" in host:
        collector = WeixinCollector()
        item = await collector.fetch(url)
    elif "bilibili.com" in host:
        collector = BilibiliCollector()
        item = await collector.fetch(url)
        if item.type == "video":
            try:
                await collector.enrich_video(item)
            except Exception:  # noqa: BLE001
                pass
        if with_comments:
            comments = await collector.fetch_comments(url)
            item.layers["comments"] = comments
            item.layers["comments_summary"] = await summarize_comments(comments, no_ai=no_ai)
    else:
        item = await WebCollector().fetch(url)
    save_item(item)
    card_path = export_card(item, get_data_dir() / "cards")
    return {"item": item, "card_path": str(card_path)}
