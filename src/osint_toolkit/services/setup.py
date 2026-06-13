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

_LAST_SYNC_FILE = "last_full_sync.txt"


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


def record_full_sync() -> None:
    """Mark that a full sync completed successfully."""
    path = get_data_dir() / _LAST_SYNC_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(datetime.now(UTC).isoformat(), encoding="utf-8")


def get_last_full_sync_at() -> str | None:
    path = get_data_dir() / _LAST_SYNC_FILE
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8").strip()
    return text or None


def _has_search_run() -> bool:
    from osint_toolkit.services import runs

    return bool(runs.list_runs(limit=1))


def get_setup_status() -> dict[str, Any]:
    auth_items = auth.get_auth_status("all")
    deepseek_ok = any(i.get("key") == "deepseek" and i.get("ok") for i in auth_items)
    bilibili_ok = any(i.get("key") == "bilibili" and i.get("ok") for i in auth_items)
    zhihu_ok = any(i.get("key") == "zhihu" and i.get("ok") for i in auth_items)
    cookies_ok = bilibili_ok or zhihu_ok

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

    last_sync = get_last_full_sync_at()
    sync_done = bool(last_sync) or event_count >= 20

    model = load_mental_model()
    brief = load_persona_brief().strip()
    persona_version = int(model.get("version", 0))
    persona_ready = bool(brief) and persona_version >= 1

    dismissed = (get_data_dir() / "setup_dismissed").exists()

    sync_detail = f"已记录 {event_count} 条行为"
    if last_sync:
        sync_detail += f"，上次完整同步 {last_sync[:19].replace('T', ' ')} UTC"

    steps = [
        {
            "id": "cookies",
            "label": "同步 Cookie",
            "done": cookies_ok,
            "required": True,
            "detail": "设置页或扩展弹窗「从浏览器同步 Cookie」",
            "href": "/settings",
        },
        {
            "id": "sync",
            "label": "完整同步行为数据",
            "done": sync_done,
            "required": True,
            "detail": sync_detail + "；等价 osint sync",
            "href": "/ingest",
        },
        {
            "id": "extension",
            "label": "安装浏览器扩展",
            "done": _extension_connected(),
            "required": False,
            "detail": "日常被动采集；加载 extension/ 目录",
            "href": "/ingest#extension",
        },
        {
            "id": "search",
            "label": "试一次搜罗",
            "done": _has_search_run(),
            "required": False,
            "detail": "验证多源采集与 AI 报告",
            "href": "/",
        },
        {
            "id": "persona",
            "label": "构建心智画像",
            "done": persona_ready,
            "required": True,
            "detail": f"画像 v{persona_version}，brief {'已生成' if brief else '未生成'}",
            "href": "/persona",
        },
    ]
    ready = all(s["done"] for s in steps if s.get("required", True))

    return {
        "ready": ready,
        "dismissed": dismissed,
        "steps": steps,
        "event_count": event_count,
        "event_types": event_types,
        "last_full_sync": last_sync,
        "persona_version": persona_version,
        "persona_stale": is_persona_stale(),
        "auth": {"deepseek": deepseek_ok, "bilibili": bilibili_ok, "zhihu": zhihu_ok},
        "tagline": "日常上网 → 一键同步 → 搜罗情报 → 构建画像",
    }


def dismiss_setup() -> None:
    flag = get_data_dir() / "setup_dismissed"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("1", encoding="utf-8")
