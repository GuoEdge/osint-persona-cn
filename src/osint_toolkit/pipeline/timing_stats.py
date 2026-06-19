"""搜罗步骤耗时统计与 ETA 校准 / Calibrated search ETA from historical step durations."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from osint_toolkit.auth.paths import get_data_dir

_STATS_FILE = "timing_stats.json"
_MAX_SAMPLES = 48
_EMA_ALPHA = 0.22

# 冷启动默认值（秒），来自典型搜罗 run 的量级
_DEFAULT_SEC: dict[str, float] = {
    "step:alias_discover": 42.0,
    "step:ai_query_analyze": 6.0,
    "step:ai_source_plan": 4.0,
    "step:collect_all": 0.0,  # 由采集子任务累加
    "step:dedup": 2.5,
    "step:mine_comments": 18.0,
    "step:ai_summarize": 28.0,
    "step:persona_simulate": 22.0,
    "step:ai_report": 38.0,
    "collect:bilibili": 11.0,
    "collect:zhihu": 9.0,
    "collect:web": 7.0,
    "collect:weixin": 10.0,
    "collect:github": 5.0,
    "collect:v2ex": 6.0,
    "collect:reddit": 8.0,
    "collect:twitter": 8.0,
    "collect:news": 7.0,
    "collect:default": 8.0,
}

_lock = threading.Lock()
_cache: dict[str, Any] | None = None


def _stats_path() -> Path:
    return get_data_dir() / _STATS_FILE


def _load_unlocked() -> dict[str, Any]:
    global _cache
    if _cache is not None:
        return _cache
    path = _stats_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                _cache = data
                return _cache
        except (json.JSONDecodeError, OSError):
            pass
    _cache = {"version": 1, "buckets": {}}
    return _cache


def _save_unlocked() -> None:
    path = _stats_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_cache or {"version": 1, "buckets": {}}, ensure_ascii=False, indent=2), encoding="utf-8")


def reset_cache_for_tests() -> None:
    global _cache
    with _lock:
        _cache = None


def record(key: str, duration_sec: float, *, min_sec: float = 0.05) -> None:
    """记录一次耗时样本（指数移动平均）。"""
    if duration_sec < min_sec:
        return
    with _lock:
        data = _load_unlocked()
        buckets: dict[str, Any] = data.setdefault("buckets", {})
        entry = buckets.get(key)
        if not isinstance(entry, dict):
            entry = {"avg_sec": duration_sec, "count": 1, "last_sec": duration_sec}
            buckets[key] = entry
        else:
            prev = float(entry.get("avg_sec") or duration_sec)
            entry["avg_sec"] = prev * (1 - _EMA_ALPHA) + duration_sec * _EMA_ALPHA
            entry["count"] = int(entry.get("count") or 0) + 1
            entry["last_sec"] = duration_sec
            samples = list(entry.get("samples") or [])
            samples.append(round(duration_sec, 3))
            if len(samples) > _MAX_SAMPLES:
                samples = samples[-_MAX_SAMPLES:]
            entry["samples"] = samples
        _save_unlocked()


def estimate(key: str) -> float:
    with _lock:
        data = _load_unlocked()
        buckets = data.get("buckets") or {}
        entry = buckets.get(key)
        if isinstance(entry, dict) and entry.get("avg_sec"):
            return max(0.1, float(entry["avg_sec"]))
    return _DEFAULT_SEC.get(key, _DEFAULT_SEC.get("collect:default", 8.0))


def _collect_key(source: str) -> str:
    return f"collect:{source}" if source else "collect:default"


def estimate_collect_task(source: str) -> float:
    return estimate(_collect_key(source))


def estimate_collect_remaining(
    tasks: list[tuple[str, str]],
    done: int,
    observed: list[tuple[str, float]] | None = None,
) -> float:
    """根据历史 per-source 耗时与本次已完成的采集任务校准剩余采集时间。"""
    pending = tasks[done:]
    if not pending:
        return 0.0

    hist_sum = sum(estimate_collect_task(src) for src, _ in pending)
    if not observed:
        return hist_sum

    source_obs: dict[str, list[float]] = {}
    for src, dur in observed:
        source_obs.setdefault(src, []).append(dur)

    run_avg = sum(d for _, d in observed) / len(observed)
    hist_avg = sum(estimate_collect_task(src) for src, _ in tasks) / max(1, len(tasks))
    if len(observed) >= 2 and hist_avg > 0.15:
        scale = max(0.35, min(2.5, 0.45 * (run_avg / hist_avg) + 0.55))
    else:
        scale = 1.0

    total = 0.0
    for src, _ in pending:
        hist = estimate_collect_task(src)
        obs_list = source_obs.get(src)
        if obs_list:
            obs_avg = sum(obs_list) / len(obs_list)
            total += 0.58 * obs_avg + 0.42 * hist
        elif len(observed) >= 2:
            total += hist * scale
        else:
            total += hist
    return total


def estimate_step_sec(step: str, *, ctx: dict[str, Any] | None = None) -> float:
    ctx = ctx or {}
    base = estimate(f"step:{step}")
    if step == "mine_comments":
        top = max(0, int(ctx.get("comment_mine_top", 12)))
        if top <= 0:
            return 0.0
        return base * max(0.25, top / 12.0)
    if step == "ai_summarize":
        n = max(1, int(ctx.get("summarize_count", 15)))
        return base * max(0.3, n / 15.0)
    if step == "persona_simulate" and ctx.get("no_simulate"):
        return 0.0
    if step == "ai_report" and not ctx.get("digest"):
        return 0.0
    return base


def planned_search_phases(
    *,
    discover_aliases: bool,
    comment_mine_top: int,
    digest: bool,
    no_simulate: bool,
) -> list[str]:
    phases: list[str] = []
    if discover_aliases:
        phases.append("alias_discover")
    phases.extend(["ai_query_analyze", "ai_source_plan", "collect_all", "dedup"])
    if comment_mine_top > 0:
        phases.append("mine_comments")
    phases.append("ai_summarize")
    if not no_simulate:
        phases.append("persona_simulate")
    if digest:
        phases.append("ai_report")
    return phases


class SearchEtaTracker:
    """搜罗全流程剩余时间估算。"""

    def __init__(
        self,
        *,
        phases: list[str],
        task_meta: list[tuple[str, str]],
        step_ctx: dict[str, Any] | None = None,
    ) -> None:
        self.phases = list(phases)
        self.task_meta = list(task_meta)
        self.step_ctx = dict(step_ctx or {})
        self.completed_steps: list[str] = []
        self.collect_observed: list[tuple[str, float]] = []

    def mark_step_completed(self, step: str, duration_ms: int) -> None:
        if duration_ms > 0:
            record(f"step:{step}", duration_ms / 1000.0)
        if step not in self.completed_steps:
            self.completed_steps.append(step)

    def record_collect_task(self, source: str, duration_sec: float) -> None:
        if duration_sec > 0:
            record(_collect_key(source), duration_sec)
            self.collect_observed.append((source, duration_sec))

    def set_task_meta(self, task_meta: list[tuple[str, str]]) -> None:
        self.task_meta = list(task_meta)

    def remaining_sec(
        self,
        *,
        current_phase: str,
        collect_done: int = 0,
    ) -> int | None:
        remaining_steps = [p for p in self.phases if p not in self.completed_steps and p != current_phase]
        # current_phase 可能正在执行，计入剩余
        if current_phase in self.phases and current_phase not in self.completed_steps:
            if current_phase not in remaining_steps:
                remaining_steps.insert(0, current_phase)

        step_sec = 0.0
        collect_sec = 0.0
        for step in remaining_steps:
            if step == "collect_all":
                collect_sec = estimate_collect_remaining(
                    self.task_meta,
                    collect_done,
                    self.collect_observed or None,
                )
            else:
                step_sec += estimate_step_sec(step, ctx=self.step_ctx)

        total = step_sec + collect_sec
        if total <= 0:
            return None
        return max(1, int(round(total)))


def ingest_run_steps(steps: list[dict[str, Any]]) -> None:
    """从已完成 run 的步骤列表回灌耗时统计。"""
    for entry in steps:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("step") or "")
        ms = int(entry.get("duration_ms") or 0)
        if not name or ms <= 0:
            continue
        record(f"step:{name}", ms / 1000.0)


def ingest_completed_run(run_dir: Path) -> None:
    """扫描 run 目录中的步骤 JSON，更新全局耗时统计。"""
    if not run_dir.is_dir():
        return
    steps: list[dict[str, Any]] = []
    manifest = run_dir / "manifest.json"
    if manifest.exists():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            for entry in data.get("steps") or []:
                if isinstance(entry, dict):
                    steps.append(entry)
        except (json.JSONDecodeError, OSError):
            pass
    if not steps:
        for path in sorted(run_dir.glob("[0-9][0-9]_*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(payload, dict) and payload.get("step"):
                steps.append(payload)
    ingest_run_steps(steps)
