"""运行记录查询 / Run record queries."""

from __future__ import annotations

import json

from osint_toolkit.auth.paths import get_data_dir


def list_runs(limit: int = 20) -> list[dict]:
    runs_dir = get_data_dir() / "runs"
    if not runs_dir.exists():
        return []
    manifests = sorted(runs_dir.glob("*/manifest.json"), reverse=True)[:limit]
    results = []
    for m in manifests:
        data = json.loads(m.read_text(encoding="utf-8"))
        data["path"] = str(m.parent)
        results.append(data)
    return results


def show_run(run_id: str, step: str | None = None) -> dict | str:
    run_dir = get_data_dir() / "runs" / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"run not found: {run_id}")
    if step:
        matches = list(run_dir.glob(f"*_{step}.json"))
        if not matches:
            raise FileNotFoundError(f"step not found: {step}")
        return json.loads(matches[0].read_text(encoding="utf-8"))
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    trace = (run_dir / "trace.log").read_text(encoding="utf-8") if (run_dir / "trace.log").exists() else ""
    manifest["trace"] = trace
    return manifest
