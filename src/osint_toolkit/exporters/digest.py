"""简报导出 / Digest export."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from osint_toolkit.auth.paths import get_data_dir
from osint_toolkit.persona.behavior_signals import score_event
from osint_toolkit.storage.sqlite import connect


def generate_daily_digest(*, use_ai: bool = False, no_ai: bool = False) -> str:
    if use_ai and not no_ai:
        from osint_toolkit.ai.digest import generate_ai_daily_digest
        from osint_toolkit.persona.context import maybe_load_persona_context

        text = generate_ai_daily_digest(maybe_load_persona_context(), no_ai=no_ai)
        out = get_data_dir() / "digests" / f"{datetime.now(UTC).date()}.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        return text

    conn = connect()
    rows = conn.execute(
        "SELECT event_type, data_json, created_at FROM events "
        "WHERE date(created_at) = date('now') ORDER BY id DESC LIMIT 80"
    ).fetchall()
    conn.close()
    lines = [f"# 每日简报 {datetime.now(UTC).date()}", "", f"今日事件: {len(rows)} 条", ""]
    ranked = []
    for row in rows:
        data = json.loads(row["data_json"])
        ranked.append((score_event(str(row["event_type"]), data), row, data))
    ranked.sort(key=lambda x: -x[0])
    for score, row, data in ranked[:40]:
        title = data.get("title") or data.get("url") or row["event_type"]
        dwell = ""
        if data.get("duration_ms"):
            dwell = f" · {int(data['duration_ms']) // 1000}s"
        lines.append(f"- [{row['event_type']}] {title}{dwell}")
    text = "\n".join(lines)
    out = get_data_dir() / "digests" / f"{datetime.now(UTC).date()}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return text
