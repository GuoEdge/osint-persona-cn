"""点赞认可导入 / Endorsement & recognition ingest."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from osint_toolkit.ingest.recognition_types import (
    INVENTORY_EVENT_TYPES,
    RECENT_EVENT_TYPES,
    RECOGNITION_EVENT_TYPES,
)
from osint_toolkit.storage.sqlite import connect


def save_endorsement(
    *,
    platform: str,
    target_type: str,
    url: str,
    content: str,
    data: dict | None = None,
) -> str:
    """Legacy table writer — deprecated; events table is the source of truth."""
    eid = str(uuid.uuid4())
    conn = connect()
    conn.execute(
        "INSERT OR REPLACE INTO endorsements (id, platform, target_type, url, content, data_json, endorsed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            eid,
            platform,
            target_type,
            url,
            content,
            json.dumps(data or {}, ensure_ascii=False),
            datetime.now(UTC).isoformat(),
        ),
    )
    conn.commit()
    conn.close()
    return eid


def list_endorsements(limit: int = 50) -> list[dict]:
    conn = connect()
    rows = conn.execute(
        "SELECT id, platform, target_type, url, content, endorsed_at FROM endorsements "
        "ORDER BY endorsed_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _title_from_event_data(data: dict[str, Any]) -> str:
    title = str(data.get("title") or "").strip()
    if title:
        return title[:200]
    message = str(data.get("message") or "").strip()
    if message:
        return message[:200]
    url = str(data.get("url") or "").strip()
    return url[:200] if url else "未命名内容"


def _recognition_summary(conn) -> dict[str, Any]:
    placeholders = ",".join("?" * len(RECOGNITION_EVENT_TYPES))
    rows = conn.execute(
        f"SELECT event_type, COUNT(DISTINCT json_extract(data_json, '$.url') || '|' || event_type) AS c "
        f"FROM events WHERE event_type IN ({placeholders}) GROUP BY event_type",
        tuple(RECOGNITION_EVENT_TYPES.keys()),
    ).fetchall()
    by_platform: dict[str, dict[str, int]] = {"zhihu": {}, "bilibili": {}, "github": {}}
    by_group: dict[str, dict[str, int]] = {"recent": {}, "inventory": {}}
    total = 0
    for row in rows:
        event_type = str(row["event_type"])
        meta = RECOGNITION_EVENT_TYPES.get(event_type)
        if not meta:
            continue
        count = int(row["c"])
        total += count
        platform = meta["platform"]
        action = meta["action"]
        group = str(meta.get("group") or "recent")
        by_platform.setdefault(platform, {})[action] = count
        by_group.setdefault(group, {})[action] = by_group.get(group, {}).get(action, 0) + count
    return {"total": total, "by_platform": by_platform, "by_group": by_group}


def _rows_for_types(conn, types: tuple[str, ...], *, limit: int) -> list:
    placeholders = ",".join("?" * len(types))
    return conn.execute(
        f"SELECT event_type, data_json, created_at FROM events "
        f"WHERE event_type IN ({placeholders}) "
        f"ORDER BY id DESC LIMIT ?",
        (*types, max(limit * 3, 120)),
    ).fetchall()


def _build_records(rows, *, limit: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        event_type = str(row["event_type"])
        meta = RECOGNITION_EVENT_TYPES.get(event_type)
        if not meta:
            continue
        data = json.loads(row["data_json"])
        url = str(data.get("url") or "").strip()
        dedup_key = (event_type, url or _title_from_event_data(data))
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        records.append(
            {
                "event_type": event_type,
                "platform": meta["platform"],
                "platform_label": meta["platform_label"],
                "action": meta["action"],
                "action_label": meta["action_label"],
                "group": meta.get("group") or "recent",
                "title": _title_from_event_data(data),
                "url": url,
                "created_at": str(row["created_at"] or ""),
                "via": str(data.get("via") or ""),
                "collection": str(data.get("collection") or ""),
            }
        )
        if len(records) >= limit:
            break
    return records


def list_recognition_records(*, limit: int = 50) -> dict[str, Any]:
    """List recent positive-engagement events used by persona (events table)."""
    types = tuple(RECOGNITION_EVENT_TYPES.keys())
    conn = connect()
    try:
        summary = _recognition_summary(conn)
        total = int(summary["total"])
        recent_rows = _rows_for_types(conn, tuple(RECENT_EVENT_TYPES), limit=limit)
        inventory_rows = _rows_for_types(conn, tuple(INVENTORY_EVENT_TYPES), limit=max(20, limit // 2))
    finally:
        conn.close()

    recent_records = _build_records(recent_rows, limit=limit)
    inventory_records = _build_records(inventory_rows, limit=max(20, limit // 2))

    hint_parts: list[str] = []
    if total == 0:
        hint_parts.append(
            "暂无行为认可数据。请先完成上方「完整同步」（需 B站/知乎 Cookie），"
            "并安装扩展以采集投币、评论等 API 无法单独拉全的行为。"
        )
    else:
        by_platform = summary.get("by_platform") or {}
        if not by_platform.get("bilibili"):
            hint_parts.append("B站点赞/投币/评论：完成完整同步或扩展被动采集后会出现。")
        zh = by_platform.get("zhihu") or {}
        if not zh.get("vote"):
            hint_parts.append(
                "知乎赞同：Cookie 同步不再拉 voteanswers（接口已废弃）；请安装扩展，日常点赞会自动记入画像。"
            )
        if not zh.get("browse"):
            hint_parts.append(
                "知乎浏览：完整同步仅导入 Edge 中的知乎链接；更多页面访问请依赖扩展被动采集。"
            )
        hint_parts.append("「收藏库快照」为账号全量收藏清单，画像中权重低于近期点赞/赞同。")

    return {
        "count": total,
        "display_count": len(recent_records) + len(inventory_records),
        "rows": recent_records + inventory_records,
        "recent": recent_records,
        "inventory": inventory_records,
        "summary": summary.get("by_platform") or {},
        "summary_by_group": summary.get("by_group") or {},
        "hint": " ".join(hint_parts),
    }
