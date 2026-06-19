"""追问服务 / Ask service."""

from __future__ import annotations

import json
from typing import Any

from osint_toolkit.ai.client import DeepSeekClient
from osint_toolkit.ai.steering import build_system_prompt
from osint_toolkit.auth.paths import get_data_dir
from osint_toolkit.persona.behavior_signals import load_ranked_behavior_samples
from osint_toolkit.persona.context import maybe_load_persona_context
from osint_toolkit.services import knowledge
from osint_toolkit.services.runs import show_run

_CONTEXT_CHARS = 14000


def _load_run_items(run_id: str, *, limit: int = 24) -> list[dict[str, Any]]:
    run_dir = get_data_dir() / "runs" / run_id
    if not run_dir.is_dir():
        return []
    for pattern in ("*items_dedup.json", "*items_raw.json"):
        paths = sorted(run_dir.glob(pattern))
        if not paths:
            continue
        try:
            raw = json.loads(paths[-1].read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        items_raw = raw if isinstance(raw, list) else raw.get("items") or []
        rows: list[dict[str, Any]] = []
        for item in items_raw[:limit]:
            if not isinstance(item, dict):
                continue
            personal = item.get("personal") or {}
            rows.append(
                {
                    "citation_id": personal.get("citation_id") or "",
                    "title": item.get("title") or "",
                    "url": item.get("url") or "",
                    "source": item.get("source") or "",
                    "summary": (item.get("summary") or item.get("content") or "")[:600],
                    "relevance": (item.get("signals") or {}).get("relevance"),
                }
            )
        return rows
    return []


def _build_messages(
    *,
    question: str,
    context: dict[str, Any],
    persona_brief: str,
    history: list[dict[str, str]] | None,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [
        {
            "role": "system",
            "content": build_system_prompt(
                task="追问",
                persona_brief=persona_brief,
            )
            + "\n请基于提供的报告与条目上下文作答；可引用 [cN] 标注来源。",
        },
    ]
    for turn in history or []:
        q = str(turn.get("question") or "").strip()
        a = str(turn.get("answer") or "").strip()
        if q:
            messages.append({"role": "user", "content": q})
        if a:
            messages.append({"role": "assistant", "content": a})

    context_blob = json.dumps(context, ensure_ascii=False)
    if len(context_blob) > _CONTEXT_CHARS:
        context_blob = context_blob[:_CONTEXT_CHARS] + "…(已截断)"
    messages.append(
        {
            "role": "user",
            "content": (
                f"上下文:\n{context_blob}\n\n"
                f"问题:{question}\n"
                "若问近期关注什么，优先结合 persona_brief 与 behavior_samples 回答。"
            ),
        }
    )
    return messages


def ask_question(
    question: str,
    *,
    run_id: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    context: dict[str, Any] = {}
    if run_id:
        try:
            run_data = show_run(run_id)
            context["run"] = {
                "run_id": run_id,
                "query": run_data.get("query"),
                "summary": run_data.get("summary"),
                "report": run_data.get("report"),
                "queries_used": run_data.get("queries_used"),
                "source_errors": run_data.get("source_errors"),
            }
            items = _load_run_items(run_id)
            if items:
                context["items"] = items
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
            messages=_build_messages(
                question=question,
                context=context,
                persona_brief=persona_ctx.brief if persona_ctx else "",
                history=history,
            )
        )
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "api" in msg.lower() and "key" in msg.lower():
            msg = "未配置 DeepSeek API Key，请在设置页「API 密钥」填写或设置 DEEPSEEK_API_KEY"
        return {"ok": False, "question": question, "answer": "", "error": msg, "run_id": run_id}
    return {"ok": True, "question": question, "answer": answer, "run_id": run_id}
