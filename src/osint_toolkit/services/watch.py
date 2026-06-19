"""话题监视 / Topic watches with URL diff between runs."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from osint_toolkit.auth.paths import get_data_dir
from osint_toolkit.utils.safe_path import assert_safe_id, resolve_under
from osint_toolkit.services.search import run_search
from osint_toolkit.utils.config import load_config

_INTERVAL_RE = re.compile(r"^(\d+)(h|m)$", re.IGNORECASE)
_DAILY_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


def _watch_state_dir(watch_id: str) -> Path:
    safe_id = assert_safe_id(watch_id, label="watch_id")
    path = resolve_under(get_data_dir() / "watches", safe_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _last_run_path(watch_id: str) -> Path:
    return _watch_state_dir(watch_id) / "last_run.json"


def load_watches() -> list[dict[str, Any]]:
    raw = load_config().get("watches") or []
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for entry in raw:
        if isinstance(entry, dict) and entry.get("id"):
            out.append(dict(entry))
    return out


def _load_last_run(watch_id: str) -> dict[str, Any] | None:
    path = _last_run_path(watch_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def watch_status(watch: dict[str, Any]) -> dict[str, Any]:
    watch_id = str(watch.get("id"))
    last = _load_last_run(watch_id)
    return {
        "id": watch_id,
        "query": watch.get("query"),
        "schedule": watch.get("schedule"),
        "enabled": watch.get("enabled", True) is not False,
        "sources": watch.get("sources"),
        "limit": watch.get("limit", 10),
        "profile": watch.get("profile", "default"),
        "last_run_at": last.get("run_at") if last else None,
        "last_run_id": last.get("run_id") if last else None,
        "last_new_count": last.get("new_count") if last else None,
        "url_count": len(last.get("urls") or []) if last else 0,
    }


def _extract_urls(items: list[Any]) -> list[str]:
    urls: list[str] = []
    for item in items:
        if hasattr(item, "url"):
            url = str(item.url or "").strip()
        elif isinstance(item, dict):
            url = str(item.get("url") or "").strip()
        else:
            continue
        if url.startswith("http"):
            urls.append(url)
    return sorted(set(urls))


def _find_watch(watch_id: str) -> dict[str, Any] | None:
    for watch in load_watches():
        if str(watch.get("id")) == watch_id:
            return watch
    return None


async def run_watch(watch_id: str) -> dict[str, Any]:
    watch = _find_watch(watch_id)
    if not watch:
        return {"ok": False, "error": f"watch not found: {watch_id}"}
    if watch.get("enabled") is False:
        return {"ok": False, "error": "watch disabled"}

    query = str(watch.get("query") or "").strip()
    if not query:
        return {"ok": False, "error": "watch has no query"}

    sources = watch.get("sources")
    limit = int(watch.get("limit") or 10)
    profile = str(watch.get("profile") or "default")

    result = await run_search(
        query,
        sources=sources if isinstance(sources, list) else None,
        limit=limit,
        digest=False,
        no_simulate=True,
        profile=profile,
    )

    urls = _extract_urls(result.get("items") or [])
    last = _load_last_run(watch_id)
    prev_urls = set(last.get("urls") or []) if last else set()
    new_urls = [u for u in urls if u not in prev_urls]

    payload = {
        "watch_id": watch_id,
        "run_at": datetime.now(UTC).isoformat(),
        "run_id": result.get("run_id"),
        "query": query,
        "urls": urls,
        "new_urls": new_urls,
        "new_count": len(new_urls),
        "total_count": len(urls),
    }
    _last_run_path(watch_id).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "ok": True,
        **payload,
        "source_errors": result.get("source_errors") or [],
        "queries_used": result.get("queries_used") or [],
        "collect_sources": result.get("collect_sources") or [],
    }


def _parse_last_run_at(last: dict[str, Any] | None) -> datetime | None:
    if not last:
        return None
    raw = last.get("run_at")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def should_run_watch(watch: dict[str, Any], *, now: datetime | None = None) -> bool:
    if watch.get("enabled") is False:
        return False
    schedule = str(watch.get("schedule") or "").strip()
    if not schedule:
        return False

    now = now or datetime.now(UTC)
    watch_id = str(watch.get("id"))
    last_at = _parse_last_run_at(_load_last_run(watch_id))

    interval_match = _INTERVAL_RE.match(schedule)
    if interval_match:
        amount = int(interval_match.group(1))
        unit = interval_match.group(2).lower()
        delta = timedelta(hours=amount) if unit == "h" else timedelta(minutes=amount)
        if last_at is None:
            return True
        return now - last_at.astimezone(UTC) >= delta

    daily_match = _DAILY_TIME_RE.match(schedule)
    if daily_match:
        hour = int(daily_match.group(1))
        minute = int(daily_match.group(2))
        if hour > 23 or minute > 59:
            return False
        slot = now.astimezone(UTC).replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now < slot:
            return False
        if last_at is None:
            return True
        last_utc = last_at.astimezone(UTC)
        if last_utc >= slot:
            return False
        return True

    return False


async def run_due_watches() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for watch in load_watches():
        if not should_run_watch(watch):
            continue
        watch_id = str(watch.get("id"))
        try:
            results.append(await run_watch(watch_id))
        except Exception as exc:  # noqa: BLE001
            results.append({"ok": False, "watch_id": watch_id, "error": str(exc)})
    return results
