"""知识库服务 / Knowledge base service."""

from __future__ import annotations

import json
from typing import Any

from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.persona.behavior_signals import score_event
from osint_toolkit.storage.knowledge import recall as _recall
from osint_toolkit.storage.sqlite import connect


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
    rows = conn.execute(
        "SELECT event_type, data_json FROM events "
        "WHERE data_json LIKE ? ORDER BY id DESC LIMIT ?",
        (f"%{q}%", remaining * 5),
    ).fetchall()
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
