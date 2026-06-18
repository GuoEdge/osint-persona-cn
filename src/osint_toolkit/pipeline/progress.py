"""搜罗/后台任务进度（内存态 + 磁盘快照，供 Web SSE / 轮询）。"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import Any

from osint_toolkit.auth.paths import get_data_dir

_store: dict[str, dict[str, Any]] = {}
_cancelled: set[str] = set()
_last_disk_flush: dict[str, float] = {}
_DISK_FLUSH_SEC = 1.0


class JobCancelled(Exception):
    """用户或系统取消了后台任务。"""


def init_progress(run_id: str, *, step_total: int = 0, phases: list[str] | None = None) -> None:
    _store[run_id] = {
        "phase": "starting",
        "detail": "正在启动…",
        "started_at": datetime.now(UTC).isoformat(),
        "completed_steps": [],
        "collect_done": 0,
        "collect_total": 0,
        "items_found": 0,
        "eta_sec": None,
        "current_url": "",
        "recent_urls": [],
        "partial_items": [],
        "step_total": step_total,
        "step_done": 0,
        "phases": phases or [],
        "percent": 0,
    }
    _flush_progress_disk(run_id, force=True)


def clear_progress(run_id: str) -> None:
    _store.pop(run_id, None)
    _cancelled.discard(run_id)
    _last_disk_flush.pop(run_id, None)


def get_progress(run_id: str) -> dict[str, Any] | None:
    mem = _store.get(run_id)
    if mem:
        return mem
    return _read_progress_disk(run_id)


def request_cancel(run_id: str) -> None:
    _cancelled.add(run_id)


def is_cancelled(run_id: str) -> bool:
    return run_id in _cancelled


def check_cancelled(run_id: str | None) -> None:
    if run_id and run_id in _cancelled:
        raise JobCancelled("任务已取消")


def _read_progress_disk(run_id: str) -> dict[str, Any] | None:
    path = get_data_dir() / "runs" / run_id / "progress.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _flush_progress_disk(run_id: str, state: dict[str, Any] | None = None, *, force: bool = False) -> None:
    now = time.monotonic()
    last = _last_disk_flush.get(run_id, 0.0)
    if not force and now - last < _DISK_FLUSH_SEC:
        return
    payload = state if state is not None else _store.get(run_id)
    if not payload:
        return
    run_path = get_data_dir() / "runs" / run_id
    run_path.mkdir(parents=True, exist_ok=True)
    (run_path / "progress.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _last_disk_flush[run_id] = now


def update_progress(
    run_id: str | None,
    phase: str,
    *,
    detail: str = "",
    mark_completed: dict[str, Any] | None = None,
    partial_items_append: list[dict[str, Any]] | None = None,
    **extra: Any,
) -> None:
    if not run_id:
        return
    state = _store.setdefault(
        run_id,
        {
            "phase": phase,
            "detail": detail,
            "started_at": datetime.now(UTC).isoformat(),
            "completed_steps": [],
            "partial_items": [],
        },
    )
    prev_phase = state.get("phase")
    state["phase"] = phase
    if detail:
        state["detail"] = detail
    if mark_completed:
        completed = list(state.get("completed_steps") or [])
        completed.append(mark_completed)
        state["completed_steps"] = completed
    if partial_items_append:
        bucket = list(state.get("partial_items") or [])
        seen = {str(x.get("id") or x.get("url") or "") for x in bucket}
        for item in partial_items_append:
            key = str(item.get("id") or item.get("url") or "")
            if key and key in seen:
                continue
            bucket.append(item)
            seen.add(key)
        state["partial_items"] = bucket[-40:]
        state["items_found"] = len(bucket)
    for key, val in extra.items():
        if val is not None:
            state[key] = val
    step_total = int(state.get("step_total") or 0)
    step_done = int(state.get("step_done") or 0)
    if step_total > 0:
        state["percent"] = min(100, int(round(step_done / step_total * 100)))
    elif state.get("collect_total"):
        total = int(state["collect_total"])
        done = int(state.get("collect_done") or 0)
        if total > 0:
            state["percent"] = min(100, int(round(done / total * 100)))
    force = extra.pop("force_disk", False)
    phase_changed = prev_phase != phase
    _flush_progress_disk(run_id, state, force=force or phase_changed or mark_completed is not None)
