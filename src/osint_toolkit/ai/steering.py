"""AI 导向控制 / AI steering and directives."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

from osint_toolkit.auth.paths import get_data_dir

DEFAULT_DIRECTIVES: dict[str, Any] = {
    "hard_constraints": [
        "不替用户做最终有价值/无价值的裁决",
        "区分事实、作者主张、社区主观感受",
        "无字幕的B站视频须标注未分析画面",
        "不静默隐藏任何采集结果",
    ],
    "soft_preferences": [
        "摘要优先提取实操步骤与踩坑",
        "反感营销软文和标题党",
        "报告语气简洁",
    ],
    "report_focus": [
        "执行摘要不超过3条",
        "必须包含争议点与待核实项",
        "模拟判断须附置信度与依据",
    ],
    "enabled_steps": {
        "query_analyze": True,
        "summarize": True,
        "report": True,
        "persona_simulate": True,
        "comment_mine": True,
        "danmaku_interpret": False,
    },
}


def directives_path() -> Path:
    return get_data_dir() / "ai_directives.yaml"


def load_directives() -> dict[str, Any]:
    path = directives_path()
    if not path.exists():
        return dict(DEFAULT_DIRECTIVES)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    merged = dict(DEFAULT_DIRECTIVES)
    for key, value in data.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return merged


def save_directives(data: dict[str, Any]) -> Path:
    path = directives_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def is_step_enabled(step: str, *, no_ai: bool = False, disabled_steps: list[str] | None = None) -> bool:
    if no_ai:
        return False
    if disabled_steps and step in disabled_steps:
        return False
    directives = load_directives()
    enabled = directives.get("enabled_steps", {})
    return bool(enabled.get(step, True))


def build_system_prompt(
    *,
    task: str,
    runtime_instruct: str = "",
    persona_brief: str = "",
) -> str:
    directives = load_directives()
    parts = [
        "你是个人情报分析助手，不是价值裁判。",
        f"当前任务: {task}",
        "硬约束（绝不可违反）:",
        *[f"- {c}" for c in directives.get("hard_constraints", [])],
        "软偏好:",
        *[f"- {p}" for p in directives.get("soft_preferences", [])],
        "报告导向:",
        *[f"- {r}" for r in directives.get("report_focus", [])],
    ]
    if persona_brief:
        parts.extend(["用户心智画像:", persona_brief])
    if runtime_instruct:
        parts.extend(["本次临时指令:", runtime_instruct])
    return "\n".join(parts)


def directives_hash() -> str:
    content = yaml.dump(load_directives(), allow_unicode=True, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()[:12]
