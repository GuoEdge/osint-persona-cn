"""AI 每日简报 / AI-powered daily digest."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from osint_toolkit.ai.client import DeepSeekClient
from osint_toolkit.ai.steering import build_system_prompt, is_step_enabled
from osint_toolkit.persona.behavior_signals import score_event
from osint_toolkit.persona.context import PersonaContext
from osint_toolkit.storage.sqlite import connect


def _today_events(*, limit: int = 80) -> list[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT event_type, data_json, created_at FROM events "
            "WHERE date(created_at) = date('now') ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    ranked = []
    for row in rows:
        data = json.loads(row["data_json"])
        ranked.append(
            {
                "event_type": row["event_type"],
                "created_at": row["created_at"],
                "score": score_event(str(row["event_type"]), data),
                "title": data.get("title") or data.get("message") or data.get("url") or "",
                "url": data.get("url") or "",
                "source": data.get("source") or "",
            }
        )
    ranked.sort(key=lambda x: -x["score"])
    return ranked[:40]


def _today_intel(*, limit: int = 20) -> list[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT title, url, source, created_at FROM intel_items "
            "WHERE date(created_at) = date('now') ORDER BY rowid DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "title": row["title"],
            "url": row["url"],
            "source": row["source"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def generate_ai_daily_digest(
    persona_ctx: PersonaContext | None = None,
    *,
    no_ai: bool = False,
) -> str:
    events = _today_events()
    intel = _today_intel()
    if no_ai or not is_step_enabled("report", no_ai=no_ai):
        lines = [f"# 每日简报 {datetime.now(UTC).date()}", ""]
        for ev in events[:20]:
            lines.append(f"- [{ev['event_type']}] {ev['title']}")
        for item in intel[:10]:
            lines.append(f"- [收录] {item['title']}")
        return "\n".join(lines)

    client = DeepSeekClient()
    brief = persona_ctx.brief if persona_ctx else ""
    payload = {
        "date": str(datetime.now(UTC).date()),
        "events": events,
        "new_intel": intel,
        "interest_hints": (persona_ctx.interest_hints[:8] if persona_ctx else []),
    }
    return client.chat(
        messages=[
            {
                "role": "system",
                "content": build_system_prompt(task="每日情报简报", persona_brief=brief),
            },
            {
                "role": "user",
                "content": (
                    "根据今日行为事件与新收录内容，写 3 段 Markdown 简报："
                    "1) 今日关注主题 2) 值得深挖 3) 与近期兴趣的关联。\n"
                    f"数据:\n{json.dumps(payload, ensure_ascii=False)[:10000]}"
                ),
            },
        ]
    )
