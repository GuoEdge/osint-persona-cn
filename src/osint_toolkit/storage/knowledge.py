"""知识库操作 / Knowledge base operations."""

from __future__ import annotations

import json
import logging
from typing import Any

from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.storage.sqlite import connect

logger = logging.getLogger(__name__)


def save_item(item: IntelItem) -> None:
    conn = connect()
    try:
        existing = conn.execute("SELECT id FROM intel_items WHERE url = ?", (item.url,)).fetchone()
        if existing and existing["id"] != item.id:
            item.id = existing["id"]
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
    finally:
        conn.close()


def recall(query: str, limit: int = 20) -> list[IntelItem]:
    q = query.strip()
    if not q:
        return []
    conn = connect()
    items: list[IntelItem] = []
    try:
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
        except Exception as exc:  # noqa: BLE001
            logger.warning("FTS recall failed, falling back to LIKE: %s", exc)
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
        return items
    finally:
        conn.close()


def delete_item(item_id: str) -> bool:
    """删除单条知识库条目。返回是否成功删除。"""
    conn = connect()
    try:
        cur = conn.execute("SELECT 1 FROM intel_items WHERE id = ?", (item_id,))
        if not cur.fetchone():
            return False
        conn.execute("DELETE FROM intel_fts WHERE item_id = ?", (item_id,))
        conn.execute("DELETE FROM intel_items WHERE id = ?", (item_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def delete_items(item_ids: list[str]) -> int:
    """批量删除知识库条目。返回实际删除条数。"""
    if not item_ids:
        return 0
    conn = connect()
    try:
        placeholders = ",".join("?" * len(item_ids))
        existing = conn.execute(
            f"SELECT id FROM intel_items WHERE id IN ({placeholders})", item_ids
        ).fetchall()
        existing_ids = [row["id"] for row in existing]
        if not existing_ids:
            return 0
        placeholders2 = ",".join("?" * len(existing_ids))
        conn.execute(f"DELETE FROM intel_fts WHERE item_id IN ({placeholders2})", existing_ids)
        conn.execute(f"DELETE FROM intel_items WHERE id IN ({placeholders2})", existing_ids)
        conn.commit()
        return len(existing_ids)
    finally:
        conn.close()


def log_event(event_type: str, data: dict[str, Any]) -> None:
    conn = connect()
    try:
        conn.execute(
            "INSERT INTO events (event_type, data_json) VALUES (?, ?)",
            (event_type, json.dumps(data, ensure_ascii=False)),
        )
        conn.commit()
    finally:
        conn.close()


def log_event_deduped(event_type: str, data: dict[str, Any], dedup_key: str) -> bool:
    """写入 events；dedup_key 已存在则跳过。返回是否新写入。"""
    conn = connect()
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO event_dedup (dedup_key, event_type) VALUES (?, ?)",
            (dedup_key, event_type),
        )
        if cur.rowcount == 0:
            return False
        conn.execute(
            "INSERT INTO events (event_type, data_json) VALUES (?, ?)",
            (event_type, json.dumps(data, ensure_ascii=False)),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def log_events_batch(entries: list[tuple[str, dict[str, Any], str]]) -> int:
    """批量写入带去重的事件。entries 为 (event_type, data, dedup_key) 列表。

    单次 connect → executemany → commit → close，替代循环调用 log_event_deduped。
    返回新写入条数。
    """
    if not entries:
        return 0
    conn = connect()
    try:
        new_rows: list[tuple[str, str, str]] = []
        for event_type, data, dedup_key in entries:
            cur = conn.execute(
                "INSERT OR IGNORE INTO event_dedup (dedup_key, event_type) VALUES (?, ?)",
                (dedup_key, event_type),
            )
            if cur.rowcount > 0:
                new_rows.append((event_type, json.dumps(data, ensure_ascii=False), dedup_key))
        if new_rows:
            conn.executemany(
                "INSERT INTO events (event_type, data_json) VALUES (?, ?)",
                [(r[0], r[1]) for r in new_rows],
            )
        conn.commit()
        return len(new_rows)
    finally:
        conn.close()
