"""追问服务 / Ask service."""

from __future__ import annotations

import json
from typing import Any

from osint_toolkit.ai.client import DeepSeekClient
from osint_toolkit.ai.steering import build_system_prompt
from osint_toolkit.persona.behavior_signals import load_ranked_behavior_samples
from osint_toolkit.persona.context import maybe_load_persona_context
from osint_toolkit.services import knowledge
from osint_toolkit.services.runs import show_run


def ask_question(question: str, *, run_id: str | None = None) -> dict[str, Any]:
    context: dict[str, Any] = {}
    if run_id:
        try:
            context["run"] = show_run(run_id)
        except FileNotFoundError:
            context["run_error"] = f"run not found: {run_id}"

    persona_ctx = maybe_load_persona_context()
    if persona_ctx:
        context["persona_brief"] = persona_ctx.brief[:2000]
        context["interest_hints"] = persona_ctx.interest_hints[:10]
        context["recent_topics"] = persona_ctx.recent_topics

    context["behavior_samples"] = load_ranked_behavior_samples(sample_limit=10)
    recalled = knowledge.recall(question, limit=5)
    if recalled:
        context["knowledge_recall"] = [
            {"title": i.title, "url": i.url, "summary": (i.summary or i.content[:300])} for i in recalled
        ]

    try:
        client = DeepSeekClient()
        answer = client.chat(
            messages=[
                {
                    "role": "system",
                    "content": build_system_prompt(
                        task="追问",
                        persona_brief=persona_ctx.brief if persona_ctx else "",
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"上下文:{json.dumps(context, ensure_ascii=False)[:8000]}\n"
                        f"问题:{question}\n"
                        "若问近期关注什么，优先结合 persona_brief 与 behavior_samples 回答。"
                    ),
                },
            ]
        )
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "api" in msg.lower() and "key" in msg.lower():
            msg = "未配置 DeepSeek API Key，请在设置中配置或设置 DEEPSEEK_API_KEY"
        return {"ok": False, "question": question, "answer": "", "error": msg, "run_id": run_id}
    return {"ok": True, "question": question, "answer": answer, "run_id": run_id}
