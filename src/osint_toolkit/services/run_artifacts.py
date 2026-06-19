"""从 run 目录加载步骤产物 / Load persisted run step artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_step_json(path: Path) -> dict[str, Any] | list[Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if isinstance(raw, dict) and "data" in raw:
        return raw.get("data")
    return raw


def load_query_analysis_from_run(run_dir: Path) -> dict[str, Any]:
    """合并 query_analysis.json 与 source_plan.json。"""
    query_analysis: dict[str, Any] = {}
    for path in sorted(run_dir.glob("*query_analysis.json")):
        payload = _load_step_json(path)
        if isinstance(payload, dict):
            query_analysis = payload
            break
    for path in sorted(run_dir.glob("*source_plan.json")):
        plan_data = _load_step_json(path)
        if isinstance(plan_data, dict):
            query_analysis.setdefault("source_plan", plan_data.get("source_plan") or {})
            query_analysis.setdefault("source_routing", plan_data.get("source_routing") or {})
            if plan_data.get("active_sources"):
                query_analysis.setdefault("active_sources", plan_data.get("active_sources"))
            break
    return query_analysis
