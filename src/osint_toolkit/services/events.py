"""行为事件查询 / Behavior events service."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from osint_toolkit.storage.sqlite import connect

_EVENT_COUNT_CACHE: dict[str, Any] = {"total": 0, "at": 0.0}
_EVENT_COUNT_TTL_SEC = 60.0


def prune_old_events(*, older_than_days: int = 90) -> dict[str, int]:
    """删除过期行为事件与去重键。"""
    if older_than_days <= 0:
        return {"events": 0, "dedup": 0}
    cutoff = (datetime.now(UTC) - timedelta(days=older_than_days)).isoformat()
    conn = connect()
    try:
        cur = conn.execute("DELETE FROM events WHERE created_at < ?", (cutoff,))
        events_deleted = int(cur.rowcount or 0)
        cur2 = conn.execute("DELETE FROM event_dedup WHERE created_at < ?", (cutoff,))
        dedup_deleted = int(cur2.rowcount or 0)
        conn.commit()
    finally:
        conn.close()
    _EVENT_COUNT_CACHE["at"] = 0.0
    return {"events": events_deleted, "dedup": dedup_deleted}


def _cached_event_total(conn) -> int:
    import time

    now = time.monotonic()
    if now - float(_EVENT_COUNT_CACHE.get("at") or 0) < _EVENT_COUNT_TTL_SEC:
        return int(_EVENT_COUNT_CACHE.get("total") or 0)
    row = conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()
    total = int(row["c"]) if row else 0
    _EVENT_COUNT_CACHE["total"] = total
    _EVENT_COUNT_CACHE["at"] = now
    return total


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
    try:
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
        total = _cached_event_total(conn)
    finally:
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
    return {"items": items, "total": total, "count": len(items)}
