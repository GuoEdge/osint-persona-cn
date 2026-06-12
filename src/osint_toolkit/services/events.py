"""行为事件查询 / Behavior events service."""

from __future__ import annotations

import json
from typing import Any

from osint_toolkit.storage.sqlite import connect


def list_recent_events(
    *,
    limit: int = 50,
    offset: int = 0,
    via: str | None = None,
    event_type: str | None = None,
    min_score: int = 0,
) -> dict[str, Any]:
    from osint_toolkit.persona.behavior_signals import score_event

    conn = connect()
    sql = "SELECT id, event_type, data_json, created_at FROM events WHERE 1=1"
    params: list[Any] = []
    if via:
        sql += " AND json_extract(data_json, '$.via') = ?"
        params.append(via)
    if event_type:
        sql += " AND event_type = ?"
        params.append(event_type)
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit + 200, offset])
    rows = conn.execute(sql, params).fetchall()
    total_row = conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()
    conn.close()

    items: list[dict[str, Any]] = []
    for row in rows:
        data = json.loads(row["data_json"])
        score = score_event(str(row["event_type"]), data)
        if score < min_score:
            continue
        items.append(
            {
                "id": row["id"],
                "event_type": row["event_type"],
                "created_at": row["created_at"],
                "score": score,
                "title": data.get("title", ""),
                "url": data.get("url", ""),
                "source": data.get("source", ""),
                "duration_ms": data.get("duration_ms"),
                "via": data.get("via", ""),
            }
        )
        if len(items) >= limit:
            break
    return {"items": items, "total": int(total_row["c"]) if total_row else 0, "count": len(items)}
