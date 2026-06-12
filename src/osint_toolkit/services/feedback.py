"""反馈服务 / Feedback service."""

from __future__ import annotations

from typing import Any

from osint_toolkit.feedback.apply import apply_step_feedback
from osint_toolkit.feedback.store import FeedbackStore


def submit_feedback(
    *,
    target_id: str,
    rating: str,
    reason: str = "",
    run_id: str | None = None,
    step: str | None = None,
    target_type: str = "item",
    sim_verdict: str = "",
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if step:
        result["step_feedback"] = apply_step_feedback(rating, reason, step=step)
    if sim_verdict and not reason:
        reason = sim_verdict
    store = FeedbackStore()
    entry = store.add(
        target_type=target_type,
        target_id=target_id,
        rating=rating,
        reason=reason,
        run_id=run_id,
        step=step,
    )
    result["entry"] = entry
    return result


def get_feedback_map(target_ids: list[str] | None = None) -> dict[str, str]:
    return FeedbackStore().map_latest_by_target(target_ids)
