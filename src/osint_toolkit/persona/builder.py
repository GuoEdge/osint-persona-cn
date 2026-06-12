"""Persona 构建 / Persona builder."""

from __future__ import annotations

import json
import shutil
from collections import Counter
from typing import Any

from osint_toolkit.ai.client import DeepSeekClient
from osint_toolkit.feedback.store import FeedbackStore
from osint_toolkit.persona.behavior_signals import load_ranked_behavior_samples, load_recent_interest_hints
from osint_toolkit.persona.context import mark_persona_built
from osint_toolkit.persona.store import (
    load_mental_model,
    load_persona_brief,
    mental_model_path,
    persona_dir,
    save_mental_model,
    save_persona_brief,
)
from osint_toolkit.storage.sqlite import connect


def _archive_model_version(version: int) -> None:
    if version < 1:
        return
    src = mental_model_path()
    if not src.exists():
        return
    dst = persona_dir() / f"mental_model.v{version}.yaml"
    if not dst.exists():
        shutil.copy2(src, dst)


def build_persona_draft(
    *,
    use_ai: bool = True,
    event_limit: int = 500,
    feedback_limit: int = 500,
    review: bool = False,
) -> dict[str, Any]:
    old_brief = load_persona_brief()
    old_hints = load_recent_interest_hints(limit=8)
    conn = connect()
    rows = conn.execute(
        "SELECT event_type, data_json FROM events ORDER BY id DESC LIMIT ?",
        (event_limit,),
    ).fetchall()
    conn.close()
    all_feedback = FeedbackStore().list_recent(feedback_limit)
    feedback = all_feedback
    sim_feedback = [f for f in all_feedback if f.get("target_type") == "simulation"]
    sources = Counter()
    event_types = Counter()
    for row in rows:
        data = json.loads(row["data_json"])
        sources[data.get("source", "unknown")] += 1
        event_types[row["event_type"]] += 1
    ranked_sample = load_ranked_behavior_samples(fetch_limit=event_limit, sample_limit=40)
    interest_hints = load_recent_interest_hints(limit=15)
    model = load_mental_model()
    old_version = int(model.get("version", 1))
    _archive_model_version(old_version)
    model["version"] = old_version + 1
    model["recent_sources"] = dict(sources)
    model["recent_event_types"] = dict(event_types)
    model["feedback_count"] = len(feedback)
    model["sim_feedback_count"] = len(sim_feedback)
    model["sample_size"] = {"events": len(rows), "feedback": len(feedback)}
    model["high_interest_hints"] = interest_hints
    save_mental_model(model)
    _archive_model_version(int(model["version"]))
    brief = f"用户近期主要关注源: {dict(sources)}; 反馈条目: {len(feedback)}"
    if use_ai:
        try:
            client = DeepSeekClient()
            brief = client.chat(
                messages=[
                    {"role": "system", "content": "根据用户行为数据生成简短persona brief，供模拟判断使用。高停留、点赞、收藏权重更高。"},
                    {
                        "role": "user",
                        "content": str(
                            {
                                "sources": dict(sources),
                                "event_types": dict(event_types),
                                "feedback": feedback[:100],
                                "simulation_feedback": sim_feedback[:50],
                                "ranked_behavior_sample": ranked_sample,
                                "high_interest_hints": interest_hints,
                            }
                        )[:12000],
                    },
                ]
            )
        except Exception:  # noqa: BLE001
            pass
    save_persona_brief(brief)
    mark_persona_built()
    from osint_toolkit.persona.auto_rebuild import set_pending_rebuild_flag

    set_pending_rebuild_flag(False)
    result: dict[str, Any] = {"mental_model": model, "persona_brief": brief}
    if review:
        result["review_summary"] = {
            "brief_before": old_brief[:800],
            "brief_after": brief[:800],
            "interest_hints_before": old_hints,
            "interest_hints_after": interest_hints[:8],
        }
    return result
