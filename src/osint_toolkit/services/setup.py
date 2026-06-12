"""首次使用 / Setup status."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from osint_toolkit.auth.paths import get_data_dir
from osint_toolkit.persona.context import is_persona_stale
from osint_toolkit.persona.store import load_mental_model, load_persona_brief
from osint_toolkit.services import auth
from osint_toolkit.storage.sqlite import connect


def _extension_connected() -> bool:
    from osint_toolkit.services import extension

    status = extension.get_extension_status()
    if not status.get("last_seen"):
        return False
    try:
        last = datetime.fromisoformat(str(status["last_seen"]).replace("Z", "+00:00"))
        return (datetime.now(UTC) - last).total_seconds() < 86400 * 7
    except ValueError:
        return bool(status.get("extension_event_count", 0) > 0)


def get_setup_status() -> dict[str, Any]:
    auth_items = auth.get_auth_status("all")
    deepseek_ok = any(i.get("key") == "deepseek" and i.get("ok") for i in auth_items)
    bilibili_ok = any(i.get("key") == "bilibili" and i.get("ok") for i in auth_items)
    zhihu_ok = any(i.get("key") == "zhihu" and i.get("ok") for i in auth_items)

    event_count = 0
    event_types: dict[str, int] = {}
    conn = connect()
    try:
        row = conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()
        event_count = int(row["c"]) if row else 0
        for erow in conn.execute("SELECT event_type, COUNT(*) AS c FROM events GROUP BY event_type"):
            event_types[str(erow["event_type"])] = int(erow["c"])
    finally:
        conn.close()

    model = load_mental_model()
    brief = load_persona_brief().strip()
    persona_version = int(model.get("version", 0))
    persona_ready = bool(brief) and event_count >= 50 and persona_version >= 1

    dismissed = (get_data_dir() / "setup_dismissed").exists()

    steps = [
        {
            "id": "auth",
            "label": "连接 DeepSeek 与 Cookie",
            "done": deepseek_ok and (bilibili_ok or zhihu_ok),
            "detail": "设置页同步 Cookie，并配置 DEEPSEEK_API_KEY",
            "href": "/settings",
        },
        {
            "id": "extension",
            "label": "安装浏览器扩展",
            "done": _extension_connected(),
            "detail": "加载 extension/ 目录，浏览 B 站/知乎补全行为",
            "href": "/ingest#extension",
        },
        {
            "id": "ingest",
            "label": "导入社交行为",
            "done": event_count >= 50,
            "detail": f"已记录 {event_count} 条行为（建议 ≥50）",
            "href": "/ingest",
        },
        {
            "id": "persona",
            "label": "构建心智画像",
            "done": persona_ready,
            "detail": f"画像 v{persona_version}，brief {'已生成' if brief else '未生成'}",
            "href": "/persona",
        },
    ]
    ready = all(s["done"] for s in steps)

    return {
        "ready": ready,
        "dismissed": dismissed,
        "steps": steps,
        "event_count": event_count,
        "event_types": event_types,
        "persona_version": persona_version,
        "persona_stale": is_persona_stale(),
        "auth": {"deepseek": deepseek_ok, "bilibili": bilibili_ok, "zhihu": zhihu_ok},
    }


def dismiss_setup() -> None:
    flag = get_data_dir() / "setup_dismissed"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("1", encoding="utf-8")
