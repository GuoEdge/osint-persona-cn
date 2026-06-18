"""简报导出 / Digest export."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

from osint_toolkit.auth.paths import get_data_dir
from osint_toolkit.persona.behavior_signals import score_event
from osint_toolkit.storage.sqlite import connect


def _zhihu_hot_list_lines_sync(*, limit: int = 15) -> list[str]:
    from osint_toolkit.ingest import zhihu_openapi

    if not zhihu_openapi.openapi_enabled("hot_list"):
        return []
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        items = asyncio.run(zhihu_openapi.hot_list(limit=limit))
    else:
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            items = pool.submit(asyncio.run, zhihu_openapi.hot_list(limit=limit)).result(timeout=30)
    if not items:
        return []
    lines = ["## 知乎热榜", ""]
    for index, item in enumerate(items, 1):
        lines.append(f"{index}. {item.title} — {item.url}")
    lines.append("")
    return lines


def generate_daily_digest(
    *,
    use_ai: bool = False,
    no_ai: bool = False,
    include_hot_list: bool = True,
) -> str:
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
    if include_hot_list:
        hot_lines = _zhihu_hot_list_lines_sync()
        if hot_lines:
            lines.extend(hot_lines)
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
