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
    conn.execute(
        "INSERT INTO intel_fts (title, content, summary) VALUES (?, ?, ?)",
        (item.title, item.content, item.summary),
    )
    conn.commit()
    conn.close()


def recall(query: str, limit: int = 20) -> list[IntelItem]:
    conn = connect()
    rows = conn.execute(
        "SELECT data_json FROM intel_items WHERE title LIKE ? OR content LIKE ? LIMIT ?",
        (f"%{query}%", f"%{query}%", limit),
    ).fetchall()
    conn.close()
    return [IntelItem.from_dict(json.loads(row["data_json"])) for row in rows]


def log_event(event_type: str, data: dict[str, Any]) -> None:
    conn = connect()
    conn.execute(
        "INSERT INTO events (event_type, data_json) VALUES (?, ?)",
        (event_type, json.dumps(data, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()
