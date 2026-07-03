"""反馈服务 / Feedback service."""

from __future__ import annotations

import json
from typing import Any

from osint_toolkit.feedback.apply import apply_step_feedback
from osint_toolkit.feedback.store import FeedbackStore
from osint_toolkit.services.run_session import run_dir_for_read
from osint_toolkit.storage.knowledge import log_event_deduped
from osint_toolkit.utils.atomic_write import atomic_write_text

_SIM_INTERESTS = {"interested", "neutral", "skip"}


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
    if interest not in _SIM_INTERESTS:
        return {"ok": False, "detail": "interest 必须是 interested/neutral/skip"}
    run_path = run_dir_for_read(run_id)
    if not run_path.exists():
        return {"ok": False, "detail": "run 目录不存在"}

    verdict_map = {"interested": "用户判定为有价值", "neutral": "用户判定为不确定", "skip": "用户判定为无价值"}
    if not verdict:
        verdict = verdict_map.get(interest, f"用户判定为 {interest}")

    updated_sim = False
    updated_rel = False

    sim_paths = [run_path / "simulations.json", *sorted(run_path.glob("*_simulations.json"))]
    seen_sim_paths: set[str] = set()
    for sim_path in sim_paths:
        if str(sim_path) in seen_sim_paths or not sim_path.exists():
            continue
        seen_sim_paths.add(str(sim_path))
        try:
            sims = json.loads(sim_path.read_text(encoding="utf-8"))
            if not isinstance(sims, list):
                continue
            matched = False
            for s in sims:
                if isinstance(s, dict) and s.get("item_id") == item_id:
                    s.setdefault(
                        "ai_original",
                        {
                            "interest": s.get("interest"),
                            "confidence": s.get("confidence"),
                            "verdict": s.get("verdict"),
                            "reason": s.get("reason"),
                        },
                    )
                    s["interest"] = interest
                    s["confidence"] = confidence
                    s["verdict"] = verdict
                    s["overridden"] = True
                    s["override_source"] = "user"
                    if reason:
                        s["reason"] = reason
                    else:
                        s.pop("reason", None)
                    matched = True
                    break
            if matched:
                atomic_write_text(sim_path, json.dumps(sims, ensure_ascii=False, indent=2))
                updated_sim = True
                break
        except (json.JSONDecodeError, OSError):
            continue

    item_paths = [run_path / "items_final.json", *sorted(run_path.glob("*items_dedup.json"))]
    seen_item_paths: set[str] = set()
    for dedup_path in item_paths:
        if str(dedup_path) in seen_item_paths or not dedup_path.exists():
            continue
        seen_item_paths.add(str(dedup_path))
        try:
            items = json.loads(dedup_path.read_text(encoding="utf-8"))
            if not isinstance(items, list):
                continue
            matched_item = False
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_id_field = item.get("id") or item.get("url") or ""
                if item_id_field == item_id:
                    signals = item.setdefault("signals", {})
                    if interest == "interested":
                        signals["relevance"] = max(float(signals.get("relevance", 0)), 0.7)
                        signals.pop("fold_reason", None)
                    elif interest == "skip":
                        signals["relevance"] = min(float(signals.get("relevance", 0)), 0.15)
                        signals["fold_reason"] = "用户判定无价值"
                    updated_rel = True
                    matched_item = True
                    break
            if matched_item:
                atomic_write_text(dedup_path, json.dumps(items, ensure_ascii=False, indent=2))
        except (json.JSONDecodeError, OSError):
            continue

    if not updated_sim:
        return {"ok": False, "detail": "未找到该条目的画像模拟结果", "updated_simulation": False}

    try:
        log_event_deduped(
            "sim_override",
            {"item_id": item_id, "interest": interest, "verdict": verdict, "run_id": run_id},
            dedup_key=f"sim_override:{run_id}:{item_id}",
        )
    except Exception:  # noqa: BLE001
        pass

    return {"ok": True, "updated_simulation": updated_sim, "updated_relevance": updated_rel}
