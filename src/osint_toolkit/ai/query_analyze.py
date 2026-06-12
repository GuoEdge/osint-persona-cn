"""查询意图分析 / Query analysis with persona context."""

from __future__ import annotations

import json
from typing import Any

from osint_toolkit.ai.client import DeepSeekClient
from osint_toolkit.ai.json_util import parse_json_object
from osint_toolkit.ai.prompt_loader import load_prompt
from osint_toolkit.ai.steering import build_system_prompt, is_step_enabled
from osint_toolkit.persona.context import PersonaContext


def _default_result(query: str, sources: list[str]) -> dict[str, Any]:
    return {
        "intent": query,
        "expanded_queries": [query],
        "aliases": [],
        "recommended_sources": list(sources),
    }


def analyze_query(
    query: str,
    sources: list[str],
    persona_ctx: PersonaContext | None = None,
    *,
    no_ai: bool = False,
    disabled_steps: list[str] | None = None,
) -> dict[str, Any]:
    if no_ai or not is_step_enabled("query_analyze", no_ai=no_ai, disabled_steps=disabled_steps):
        return _default_result(query, sources)

    client = DeepSeekClient()
    prompt_tpl, _ = load_prompt("query_analyze")
    brief = (persona_ctx.brief if persona_ctx else "")[:1500]
    hints = (persona_ctx.interest_hints[:5] if persona_ctx else [])

    raw = client.chat(
        messages=[
            {
                "role": "system",
                "content": build_system_prompt(task="查询分析", persona_brief=brief),
            },
            {
                "role": "user",
                "content": (
                    f"{prompt_tpl}\n\n"
                    f"用户查询: {query}\n"
                    f"当前来源: {sources}\n"
                    f"近期兴趣: {json.dumps(hints, ensure_ascii=False)}\n"
                    "输出 JSON 对象，字段: intent, expanded_queries(数组), aliases(数组), recommended_sources(数组)"
                ),
            },
        ]
    )
    parsed = parse_json_object(raw)
    if not parsed:
        return _default_result(query, sources)

    expanded = parsed.get("expanded_queries") or [query]
    if isinstance(expanded, str):
        expanded = [expanded]
    expanded = [str(q).strip() for q in expanded if str(q).strip()]

    rec_sources = parsed.get("recommended_sources") or sources
    if isinstance(rec_sources, str):
        rec_sources = [rec_sources]
    rec_sources = [str(s) for s in rec_sources if str(s) in sources] or list(sources)

    aliases = parsed.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [aliases]
    aliases = [str(a).strip() for a in aliases if str(a).strip()]

    return {
        "intent": str(parsed.get("intent") or query),
        "expanded_queries": expanded or [query],
        "aliases": aliases,
        "recommended_sources": rec_sources,
    }
