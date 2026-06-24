"""浏览器扩展接入 / Browser extension integration."""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

from osint_toolkit.auth.paths import get_data_dir
from osint_toolkit.ingest.dwell_save import collect_dwell_save_urls, knowledge_auto_dedup_key
from osint_toolkit.ingest.extension_events import normalize_extension_payload
from osint_toolkit.persona.context import refresh_persona_stale_flag
from osint_toolkit.storage.sqlite import connect
from osint_toolkit.utils.atomic_write import atomic_write_text
from osint_toolkit.utils.config import load_config

_STATUS_FILE = "extension_status.json"
logger = logging.getLogger(__name__)
_MAX_AUTO_SAVE_PER_BATCH = 5
_EVENT_STATS_CACHE_TTL_SEC = 45.0
_event_stats_cache: dict[str, Any] | None = None
_event_stats_cache_at: float = 0.0


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


def _log_ext_auto_save(url: str) -> None:
    conn = connect()
    try:
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
        conn.commit()
    finally:
        conn.close()


async def _save_to_knowledge(urls: list[str]) -> tuple[list[str], list[str]]:
    from osint_toolkit.services.save import save_url

    saved: list[str] = []
    errors: list[str] = []
    dwell_no_ai = bool(load_config().get("ai", {}).get("dwell_save_no_ai", True))
    for url in urls:
        if not url.startswith("http"):
            continue
        try:
            from osint_toolkit.http.ssrf import SSRFError, assert_public_http_url

            assert_public_http_url(url)
        except SSRFError as exc:
            errors.append(f"{url}: {exc}")
            continue
        conn = connect()
        try:
            if _url_in_knowledge(conn, url):
                continue
            dedup_key = knowledge_auto_dedup_key(url)
            if not _try_mark_dedup(conn, dedup_key, "knowledge_auto"):
                continue
            conn.commit()
        finally:
            conn.close()
        try:
            await save_url(url, no_ai=dwell_no_ai)
            saved.append(url)
            _log_ext_auto_save(url)
        except Exception as exc:  # noqa: BLE001
            msg = f"{url}: {exc}"
            logger.warning("extension auto-save failed: %s", msg)
            errors.append(msg)
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
    save_cap_note = ""
    if len(all_save) > _MAX_AUTO_SAVE_PER_BATCH:
        save_cap_note = (
            f"本批自动收录已限流：仅处理前 {_MAX_AUTO_SAVE_PER_BATCH} 条，"
            f"其余 {len(all_save) - _MAX_AUTO_SAVE_PER_BATCH} 条跳过（事件已入库）"
        )
        all_save = all_save[:_MAX_AUTO_SAVE_PER_BATCH]
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
    rebuild_info: dict[str, Any] = {"action": "none"}
    try:
        from osint_toolkit.persona.auto_rebuild import maybe_auto_rebuild_persona

        rebuild_info = await maybe_auto_rebuild_persona()
    except Exception as exc:  # noqa: BLE001
        logger.warning("extension persona rebuild skipped: %s", exc)
    try:
        stale = refresh_persona_stale_flag()
    except Exception as exc:  # noqa: BLE001
        logger.warning("extension persona stale refresh skipped: %s", exc)
        stale = False
    status["persona_stale"] = stale
    _write_status(status)
    return {
        "accepted": accepted,
        "skipped": skipped,
        "by_type": by_type,
        "saved_to_knowledge": len(saved_knowledge),
        "saved_urls": saved_knowledge[:10],
        "warnings": ([save_cap_note] if save_cap_note else []) + (auto_save_errors + parse_errors)[:5],
        "auto_save_errors": auto_save_errors[:5],
        "parse_errors": parse_errors[:5],
        "persona_rebuild_suggested": bool(rebuild_info.get("persona_rebuild_suggested")),
        "persona_rebuild_action": rebuild_info.get("action"),
    }


def _connected_from_last_seen(last_seen: str | None) -> bool:
    if not last_seen:
        return False
    try:
        dt = datetime.fromisoformat(str(last_seen).replace("Z", "+00:00"))
        return (datetime.now(UTC) - dt.astimezone(UTC)).total_seconds() < 600
    except ValueError:
        return bool(last_seen)


def read_extension_ping() -> dict[str, Any]:
    """仅读扩展心跳文件，不查库。"""
    path = _status_path()
    base: dict[str, Any] = {
        "connected": False,
        "last_seen": None,
        "api_base": "http://127.0.0.1:8787",
        "pending_queue": 0,
        "last_flush_error": "",
        "extension_version": "",
    }
    if not path.exists():
        return base
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
        base.update(stored)
        base["connected"] = _connected_from_last_seen(stored.get("last_seen"))
    except json.JSONDecodeError:
        pass
    return base


def _extension_event_stats() -> tuple[int, dict[str, int]]:
    global _event_stats_cache, _event_stats_cache_at
    now = time.monotonic()
    if _event_stats_cache is not None and now - _event_stats_cache_at < _EVENT_STATS_CACHE_TTL_SEC:
        cached = _event_stats_cache
        return int(cached.get("extension_event_count") or 0), dict(cached.get("event_totals") or {})

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
        count = int(ext_total["c"]) if ext_total else 0
    finally:
        conn.close()
    _event_stats_cache = {"extension_event_count": count, "event_totals": totals}
    _event_stats_cache_at = now
    return count, totals


def get_extension_status(*, include_stats: bool = True) -> dict[str, Any]:
    base = read_extension_ping()
    base.setdefault("event_totals", {})
    base.setdefault("extension_event_count", 0)

    if include_stats:
        count, totals = _extension_event_stats()
        base["extension_event_count"] = count
        base["event_totals"] = totals

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
    atomic_write_text(path, json.dumps(current, ensure_ascii=False, indent=2))


def ping_extension(
    version: str = "",
    enabled: bool = True,
    *,
    pending_queue: int = 0,
    last_flush_error: str = "",
) -> dict[str, Any]:
    patch: dict[str, Any] = {
        "last_seen": datetime.now(UTC).isoformat(),
        "extension_version": version,
        "enabled": enabled,
        "pending_queue": max(0, int(pending_queue)),
    }
    if last_flush_error:
        patch["last_flush_error"] = str(last_flush_error)[:500]
    elif pending_queue == 0:
        patch["last_flush_error"] = ""
    _write_status(patch)
    return {"ok": True, "server_time": datetime.now(UTC).isoformat()}
