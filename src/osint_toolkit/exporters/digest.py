"""简报导出 / Digest export."""

from __future__ import annotations

from datetime import UTC, datetime

from osint_toolkit.auth.paths import get_data_dir
from osint_toolkit.storage.sqlite import connect


def generate_daily_digest() -> str:
    conn = connect()
    rows = conn.execute(
        "SELECT event_type, data_json, created_at FROM events "
        "WHERE date(created_at) = date('now') ORDER BY id DESC LIMIT 50"
    ).fetchall()
    conn.close()
    lines = [f"# 每日简报 {datetime.now(UTC).date()}", "", f"今日事件: {len(rows)} 条", ""]
    for row in rows:
        lines.append(f"- [{row['event_type']}] {row['data_json'][:120]}")
    text = "\n".join(lines)
    out = get_data_dir() / "digests" / f"{datetime.now(UTC).date()}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return text
