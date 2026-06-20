"""知识库服务 / Knowledge base service."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from typing import Any

from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.persona.behavior_signals import score_event
from osint_toolkit.storage.knowledge import delete_item as _delete_item
from osint_toolkit.storage.knowledge import delete_items as _delete_items
from osint_toolkit.storage.knowledge import recall as _recall
from osint_toolkit.storage.sqlite import connect


def _temporal_decay(created_at_str: str | None, half_life_days: float = 30.0) -> float:
    if not created_at_str:
        return 0.5
    try:
        created = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        age_days = (datetime.now(UTC) - created).total_seconds() / 86400
        return math.pow(0.5, age_days / half_life_days)
    except (ValueError, TypeError):
        return 0.5


def recall(query: str, limit: int = 20) -> list[IntelItem]:
    items = _recall(query, limit=limit)
    q = query.strip()
    if not q:
        return items
    remaining = limit - len(items)
    if remaining <= 0:
        return items
    seen = {i.url for i in items if i.url}
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT event_type, data_json FROM events "
            "WHERE data_json LIKE ? ORDER BY id DESC LIMIT ?",
            (f"%{q}%", remaining * 5),
        ).fetchall()
    finally:
        conn.close()
    for row in rows:
        data = json.loads(row["data_json"])
        if score_event(str(row["event_type"]), data) < 12:
            continue
        url = str(data.get("url") or "")
        title = str(data.get("title") or url or row["event_type"])
        if url and url in seen:
            continue
        if url:
            seen.add(url)
        items.append(
            IntelItem(
                source=str(data.get("source") or "behavior"),
                type="behavior",
                url=url,
                title=title,
                content=f"行为信号: {row['event_type']}",
                personal={"from": "events", "event_type": row["event_type"]},
            )
        )
        if len(items) >= limit:
            break
    for item in items:
        decay = _temporal_decay(item.published_at or item.personal.get("saved_at"))
        item.signals.relevance = (item.signals.relevance or 0.5) * decay
    items.sort(key=lambda i: i.signals.relevance or 0, reverse=True)
    return items


def list_items(
    *,
    query: str = "",
    source: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[IntelItem]:
    conn = connect()
    sql = "SELECT data_json, created_at FROM intel_items WHERE 1=1"
    params: list[Any] = []
    if query:
        sql += " AND (title LIKE ? OR content LIKE ?)"
        params.extend([f"%{query}%", f"%{query}%"])
    if source:
        sql += " AND source = ?"
        params.append(source)
    sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    items = []
    for row in rows:
        item = IntelItem.from_dict(json.loads(row["data_json"]))
        item.personal["saved_at"] = row["created_at"]
        items.append(item)
    return items


def count_items(source: str | None = None) -> int:
    conn = connect()
    if source:
        row = conn.execute("SELECT COUNT(*) AS c FROM intel_items WHERE source = ?", (source,)).fetchone()
    else:
        row = conn.execute("SELECT COUNT(*) AS c FROM intel_items").fetchone()
    conn.close()
    return int(row["c"]) if row else 0


def delete_item(item_id: str) -> bool:
    """删除单条知识库条目。返回是否成功删除。"""
    return _delete_item(item_id)


def delete_items(item_ids: list[str]) -> int:
    """批量删除知识库条目。返回实际删除条数。"""
    return _delete_items(item_ids)


def list_topics(limit: int = 50) -> list[dict[str, Any]]:
    """聚合最近知识库条目的 topics 字段，按出现频率排序返回。"""
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT data_json FROM intel_items ORDER BY created_at DESC LIMIT 5000"
        ).fetchall()
    finally:
        conn.close()
    counter: dict[str, int] = {}
    for row in rows:
        try:
            data = json.loads(row["data_json"])
            for topic in data.get("topics") or []:
                if isinstance(topic, str) and topic:
                    counter[topic] = counter.get(topic, 0) + 1
        except (json.JSONDecodeError, TypeError):
            continue
    sorted_topics = sorted(counter.items(), key=lambda x: -x[1])
    return [{"topic": t, "count": c} for t, c in sorted_topics[:limit]]
