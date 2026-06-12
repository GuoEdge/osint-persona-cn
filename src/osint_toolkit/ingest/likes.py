"""点赞认可导入 / Endorsement ingest."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from osint_toolkit.storage.sqlite import connect


def save_endorsement(
    *,
    platform: str,
    target_type: str,
    url: str,
    content: str,
    data: dict | None = None,
) -> str:
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
