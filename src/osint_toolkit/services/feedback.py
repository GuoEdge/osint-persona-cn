"""反馈服务 / Feedback service."""

from __future__ import annotations

import json
from typing import Any

from osint_toolkit.feedback.apply import apply_step_feedback
from osint_toolkit.feedback.store import FeedbackStore
from osint_toolkit.services.run_session import run_dir_for_read
from osint_toolkit.utils.atomic_write import atomic_write_text


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


def override_simulation(
    *,
    run_id: str,
    item_id: str,
    interest: str = "interested",
    confidence: float = 0.9,
    verdict: str = "",
    reason: str = "",
) -> dict[str, Any]:
    """即时覆盖 run 内某条目的画像模拟判定。"""
    run_path = run_dir_for_read(run_id)
    if not run_path.exists():
        return {"ok": False, "detail": "run 目录不存在"}

    verdict_map = {"interested": "用户判定为有价值", "neutral": "用户判定为不确定", "skip": "用户判定为无价值"}
    if not verdict:
        verdict = verdict_map.get(interest, f"用户判定为 {interest}")

    updated_sim = False
    updated_rel = False

    for sim_path in sorted(run_path.glob("*_simulations.json")):
        try:
            sims = json.loads(sim_path.read_text(encoding="utf-8"))
            if not isinstance(sims, list):
                continue
            for s in sims:
                if isinstance(s, dict) and s.get("item_id") == item_id:
                    s["interest"] = interest
                    s["confidence"] = confidence
                    s["verdict"] = verdict
                    if reason:
                        s["reason"] = reason
                    else:
                        s.pop("reason", None)
                    break
            atomic_write_text(sim_path, json.dumps(sims, ensure_ascii=False, indent=2))
            updated_sim = True
            break
        except (json.JSONDecodeError, OSError):
            continue

    for dedup_path in sorted(run_path.glob("*items_dedup.json")):
        try:
            items = json.loads(dedup_path.read_text(encoding="utf-8"))
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_id_field = item.get("id") or item.get("url") or ""
                if item_id_field == item_id:
                    signals = item.setdefault("signals", {})
                    if interest == "interested":
                        signals["relevance"] = max(float(signals.get("relevance", 0)), 0.7)
                        signals.pop("fold_reason", None)
                    updated_rel = True
                    break
            atomic_write_text(dedup_path, json.dumps(items, ensure_ascii=False, indent=2))
            break
        except (json.JSONDecodeError, OSError):
            continue

    return {"ok": True, "updated_simulation": updated_sim, "updated_relevance": updated_rel}
