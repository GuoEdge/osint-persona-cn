"""搜罗 run 会话落盘 / Persist search run session to disk."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from osint_toolkit.auth.paths import get_data_dir

RUN_STATUSES = frozenset({"running", "done", "error", "cancelled", "interrupted"})


def run_dir(run_id: str) -> Path:
    return get_data_dir() / "runs" / run_id


def write_request(run_id: str, request: dict[str, Any]) -> None:
    d = run_dir(run_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "request.json").write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")


def read_request(run_id: str) -> dict[str, Any] | None:
    path = run_dir(run_id) / "request.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def patch_manifest(run_id: str, **fields: Any) -> None:
    d = run_dir(run_id)
    d.mkdir(parents=True, exist_ok=True)
    manifest_path = d / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {"run_id": run_id}
    else:
        manifest = {"run_id": run_id}
    manifest.update(fields)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def set_run_status(
    run_id: str,
    status: str,
    *,
    error: str | None = None,
    request: dict[str, Any] | None = None,
) -> None:
    if status not in RUN_STATUSES:
        raise ValueError(f"invalid status: {status}")
    now = datetime.now(UTC).isoformat()
    fields: dict[str, Any] = {"status": status}
    if request:
        fields["request"] = request
        write_request(run_id, request)
    if status == "running":
        fields.setdefault("started_at", now)
    else:
        fields["finished_at"] = now
    if error:
        fields["error"] = error
    patch_manifest(run_id, **fields)


def read_manifest(run_id: str) -> dict[str, Any] | None:
    path = run_dir(run_id) / "manifest.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def read_progress_disk(run_id: str) -> dict[str, Any] | None:
    path = run_dir(run_id) / "progress.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def mark_stale_running_as_interrupted() -> list[str]:
    """Web 启动时将仍为 running 且无活跃任务的 run 标为 interrupted。"""
    runs_root = get_data_dir() / "runs"
    if not runs_root.exists():
        return []
    touched: list[str] = []
    for manifest_path in runs_root.glob("*/manifest.json"):
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if data.get("status") != "running":
            continue
        run_id = data.get("run_id") or manifest_path.parent.name
        set_run_status(run_id, "interrupted", error="Web 服务重启，任务已中断")
        touched.append(run_id)
    return touched
