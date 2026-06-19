"""AI 管线步骤 ID 注册表 / Canonical AI step identifiers."""

from __future__ import annotations

# canonical_id -> UI label (optional)
AI_STEPS: dict[str, str] = {
    "alias_discover": "关联词发现",
    "query_analyze": "查询分析",
    "source_plan": "信源规划",
    "summarize": "AI 摘要",
    "persona_simulate": "画像模拟",
    "comment_mine": "评论挖掘",
    "report": "情报报告",
    "danmaku_interpret": "弹幕解读",
}

# Legacy / UI aliases -> canonical
_STEP_ALIASES: dict[str, str] = {
    "ai_summarize": "summarize",
    "ai_query_analyze": "query_analyze",
    "ai_source_plan": "source_plan",
    "ai_report": "report",
}


def normalize_step_id(step: str) -> str:
    s = (step or "").strip()
    return _STEP_ALIASES.get(s, s)


def normalize_disabled_steps(steps: list[str] | None) -> list[str]:
    if not steps:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in steps:
        cid = normalize_step_id(str(raw).strip())
        if not cid or cid in seen:
            continue
        seen.add(cid)
        out.append(cid)
    return out


def is_step_disabled(step: str, disabled_steps: list[str] | None) -> bool:
    cid = normalize_step_id(step)
    normalized = {normalize_step_id(s) for s in (disabled_steps or [])}
    return cid in normalized
