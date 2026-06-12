"""反馈应用逻辑 / Apply feedback to system state."""

from __future__ import annotations

from typing import Any

from osint_toolkit.feedback.store import FeedbackStore


def apply_step_feedback(rating: str, reason: str, step: str | None = None) -> dict[str, Any]:
    """记录分步反馈；若 wrong 则建议用户更新 ai_directives。"""
    store = FeedbackStore()
    entry = store.add(
        target_type="step",
        target_id=step or "unknown",
        rating=rating,
        reason=reason,
    )
    suggestion = None
    if rating == "wrong":
        suggestion = "考虑运行 osint ai directives edit 更新 hard_constraints"
    return {"entry": entry, "suggestion": suggestion}
