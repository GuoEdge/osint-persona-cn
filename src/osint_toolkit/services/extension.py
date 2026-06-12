"""浏览器扩展接入 / Browser extension integration."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from osint_toolkit.auth.paths import get_data_dir
from osint_toolkit.ingest.dwell_save import collect_dwell_save_urls, knowledge_auto_dedup_key
from osint_toolkit.ingest.extension_events import normalize_extension_payload
from osint_toolkit.persona.context import refresh_persona_stale_flag
from osint_toolkit.storage.sqlite import connect
from osint_toolkit.utils.config import load_config

_STATUS_FILE = "extension_status.json"
logger = logging.getLogger(__name__)


def _status_path():
    return get_data_dir() / _STATUS_FILE


def _try_mark_dedup(conn, dedup_key: str, event_type: str) -> bool:
    cur = conn.execute(
        "INSERT OR IGNORE INTO event_dedup (dedup_key, event_type) VALUES (?, ?)",
        (dedup_key, event_type),
    )
    return cur.rowcount > 0


def _url_in_knowledge(conn, url: str) -> bool:
    row = conn.execute("SELECT 1 FROM intel_items WHERE url = ? LIMIT 1", (url,)).fetchone()
    return row is not None


async def _save_to_knowledge(urls: list[str], *, conn=None) -> tuple[list[str], list[str]]:
    from osint_toolkit.services.save import save_url

    saved: list[str] = []
    errors: list[str] = []
    own_conn = conn is None
    if own_conn:
        conn = connect()
    try:
        for url in urls:
            if not url.startswith("http"):
                continue
            if _url_in_knowledge(conn, url):
                continue
            dedup_key = knowledge_auto_dedup_key(url)
            if not _try_mark_dedup(conn, dedup_key, "knowledge_auto"):
                continue
            try:
                dwell_no_ai = bool(load_config().get("ai", {}).get("dwell_save_no_ai", True))
                await save_url(url, no_ai=dwell_no_ai)
                saved.append(url)
                conn.execute(
                    "INSERT INTO events (event_type, data_json) VALUES (?, ?)",
                    (
                        "ext_auto_save",
                        json.dumps(
                            {"source": "extension", "url": url, "event_kind": "auto_save", "via": "extension"},
                            ensure_ascii=False,
                        ),
                    ),
                )
            except Exception as exc:  # noqa: BLE001
                msg = f"{url}: {exc}"
                logger.warning("extension auto-save failed: %s", msg)
                errors.append(msg)
        if own_conn:
            conn.commit()
    finally:
        if own_conn:
            conn.close()
    return saved, errors


async def ingest_extension_batch(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = 0
    skipped = 0
    parse_errors: list[str] = []
    by_type: dict[str, int] = {}
    save_urls = [
        str(p.get("url"))
        for p in payloads
        if p.get("kind") == "save_to_osint" and p.get("save_knowledge") and p.get("url")
    ]
    dwell_urls = collect_dwell_save_urls(payloads)
    conn = connect()
    try:
        for payload in payloads:
            try:
                normalized = normalize_extension_payload(payload)
            except Exception as exc:  # noqa: BLE001
                msg = f"{payload.get('kind') or 'event'}: {exc}"
                logger.warning("extension payload parse failed: %s", msg)
                parse_errors.append(msg)
                skipped += 1
                continue
            for event_type, data, dedup_key in normalized:
                if not _try_mark_dedup(conn, dedup_key, event_type):
                    skipped += 1
                    continue
                conn.execute(
                    "INSERT INTO events (event_type, data_json) VALUES (?, ?)",
                    (event_type, json.dumps(data, ensure_ascii=False)),
                )
                accepted += 1
                by_type[event_type] = by_type.get(event_type, 0) + 1
        conn.commit()
    finally:
        conn.close()

    auto_urls = [u for u in dwell_urls if u not in save_urls]
    all_save = list(dict.fromkeys(save_urls + auto_urls))
    saved_knowledge: list[str] = []
    auto_save_errors: list[str] = []
    if all_save:
        saved_knowledge, auto_save_errors = await _save_to_knowledge(all_save)

    status = {
        "last_seen": datetime.now(UTC).isoformat(),
        "last_batch": len(payloads),
        "last_accepted": accepted,
        "last_skipped": skipped,
        "last_by_type": by_type,
        "last_saved_knowledge": len(saved_knowledge),
    }
    from osint_toolkit.persona.auto_rebuild import maybe_auto_rebuild_persona

    rebuild_info = await maybe_auto_rebuild_persona()
    stale = refresh_persona_stale_flag()
    status["persona_stale"] = stale
    _write_status(status)
    return {
        "accepted": accepted,
        "skipped": skipped,
        "by_type": by_type,
        "saved_to_knowledge": len(saved_knowledge),
        "saved_urls": saved_knowledge[:10],
        "warnings": (auto_save_errors + parse_errors)[:5],
        "auto_save_errors": auto_save_errors[:5],
        "parse_errors": parse_errors[:5],
        "persona_rebuild_suggested": bool(rebuild_info.get("persona_rebuild_suggested")),
        "persona_rebuild_action": rebuild_info.get("action"),
    }


def get_extension_status() -> dict[str, Any]:
    path = _status_path()
    base: dict[str, Any] = {
        "connected": False,
        "last_seen": None,
        "api_base": "http://127.0.0.1:8787",
        "event_totals": {},
    }
    if path.exists():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
            base.update(stored)
            base["connected"] = bool(stored.get("last_seen"))
        except json.JSONDecodeError:
            pass

    conn = connect()
    try:
        totals: dict[str, int] = {}
        for row in conn.execute(
            "SELECT event_type, COUNT(*) AS c FROM events "
            "WHERE json_extract(data_json, '$.via') = 'extension' "
            "GROUP BY event_type"
        ):
            totals[str(row["event_type"])] = int(row["c"])
        ext_total = conn.execute(
            "SELECT COUNT(*) AS c FROM events WHERE json_extract(data_json, '$.via') = 'extension'"
        ).fetchone()
        base["extension_event_count"] = int(ext_total["c"]) if ext_total else 0
        base["event_totals"] = totals
    finally:
        conn.close()
    try:
        from osint_toolkit.persona.context import is_persona_stale

        base["persona_stale"] = is_persona_stale()
    except Exception:  # noqa: BLE001
        base["persona_stale"] = False
    return base


def _write_status(patch: dict[str, Any]) -> None:
    path = _status_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    current: dict[str, Any] = {}
    if path.exists():
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            current = {}
    current.update(patch)
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")


def ping_extension(version: str = "", enabled: bool = True) -> dict[str, Any]:
    _write_status(
        {
            "last_seen": datetime.now(UTC).isoformat(),
            "extension_version": version,
            "enabled": enabled,
        }
    )
    return {"ok": True, "server_time": datetime.now(UTC).isoformat()}
