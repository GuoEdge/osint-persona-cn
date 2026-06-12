"""知识库操作 / Knowledge base operations."""

from __future__ import annotations

import json
from typing import Any

from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.storage.sqlite import connect


def save_item(item: IntelItem) -> None:
    conn = connect()
    data = item.model_dump()
    conn.execute(
        "INSERT OR REPLACE INTO intel_items (id, source, type, url, title, content, data_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (item.id, item.source, item.type, item.url, item.title, item.content, json.dumps(data, ensure_ascii=False)),
    )
    conn.execute("DELETE FROM intel_fts WHERE item_id = ?", (item.id,))
    conn.execute(
        "INSERT INTO intel_fts (item_id, title, content, summary) VALUES (?, ?, ?, ?)",
        (item.id, item.title, item.content, item.summary or ""),
    )
    conn.commit()
    conn.close()


def recall(query: str, limit: int = 20) -> list[IntelItem]:
    q = query.strip()
    if not q:
        return []
    conn = connect()
    items: list[IntelItem] = []
    try:
        fts_query = " ".join(f'"{part}"' for part in q.split() if part)
        rows = conn.execute(
            """
            SELECT i.data_json FROM intel_fts f
            JOIN intel_items i ON i.id = f.item_id
            WHERE intel_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (fts_query, limit),
        ).fetchall()
        items = [IntelItem.from_dict(json.loads(row["data_json"])) for row in rows]
    except Exception:  # noqa: BLE001
        items = []
    if len(items) < limit:
        seen = {i.id for i in items}
        like_rows = conn.execute(
            "SELECT data_json FROM intel_items WHERE title LIKE ? OR content LIKE ? LIMIT ?",
            (f"%{q}%", f"%{q}%", limit * 2),
        ).fetchall()
        for row in like_rows:
            item = IntelItem.from_dict(json.loads(row["data_json"]))
            if item.id in seen:
                continue
            items.append(item)
            seen.add(item.id)
            if len(items) >= limit:
                break
    conn.close()
    return items


def log_event(event_type: str, data: dict[str, Any]) -> None:
    conn = connect()
    conn.execute(
        "INSERT INTO events (event_type, data_json) VALUES (?, ?)",
        (event_type, json.dumps(data, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()
