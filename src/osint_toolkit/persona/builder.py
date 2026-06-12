"""Persona 构建 / Persona builder."""

from __future__ import annotations

from collections import Counter
from typing import Any

from osint_toolkit.ai.client import DeepSeekClient
from osint_toolkit.feedback.store import FeedbackStore
from osint_toolkit.persona.store import load_mental_model, save_mental_model, save_persona_brief
from osint_toolkit.storage.knowledge import connect


def build_persona_draft(*, use_ai: bool = True) -> dict[str, Any]:
    conn = connect()
    rows = conn.execute("SELECT event_type, data_json FROM events ORDER BY id DESC LIMIT 200").fetchall()
    conn.close()
    feedback = FeedbackStore().list_recent(100)
    sources = Counter()
    for row in rows:
        import json

        data = json.loads(row["data_json"])
        sources[data.get("source", "unknown")] += 1
    model = load_mental_model()
    model["version"] = int(model.get("version", 1)) + 1
    model["recent_sources"] = dict(sources)
    model["feedback_count"] = len(feedback)
    save_mental_model(model)
    brief = f"用户近期主要关注源: {dict(sources)}; 反馈条目: {len(feedback)}"
    if use_ai:
        try:
            client = DeepSeekClient()
            brief = client.chat(
                messages=[
                    {"role": "system", "content": "根据用户行为数据生成简短persona brief，供模拟判断使用。"},
                    {"role": "user", "content": str({"sources": dict(sources), "feedback": feedback[:20]})[:6000]},
                ]
            )
        except Exception:  # noqa: BLE001
            pass
    save_persona_brief(brief)
    return {"mental_model": model, "persona_brief": brief}
