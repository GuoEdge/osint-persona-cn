"""搜罗建议 / Suggested search queries from persona."""

from __future__ import annotations

import json

from osint_toolkit.ai.client import DeepSeekClient
from osint_toolkit.ai.json_util import parse_json_array
from osint_toolkit.ai.steering import build_system_prompt, is_step_enabled
from osint_toolkit.persona.context import PersonaContext, maybe_load_persona_context


def suggest_queries(
    persona_ctx: PersonaContext | None = None,
    *,
    no_ai: bool = False,
    limit: int = 3,
) -> list[str]:
    ctx = persona_ctx or maybe_load_persona_context()
    if not ctx:
        return []

    fallback: list[str] = []
    for hint in ctx.interest_hints[:limit]:
        title = str(hint.get("title") or "").strip()
        if title and title not in fallback:
            fallback.append(title[:60])
    if len(fallback) >= limit:
        return fallback[:limit]

    if no_ai or not is_step_enabled("query_analyze", no_ai=no_ai):
        return fallback[:limit] or ctx.recent_topics[:limit]

    client = DeepSeekClient()
    raw = client.chat(
        messages=[
            {
                "role": "system",
                "content": build_system_prompt(task="搜罗建议", persona_brief=ctx.brief),
            },
            {
                "role": "user",
                "content": (
                    f"根据用户兴趣生成 {limit} 个搜罗查询词，JSON 数组，每项 {{query: string}}。\n"
                    f"兴趣: {json.dumps(ctx.interest_hints[:8], ensure_ascii=False)}\n"
                    f"主题: {ctx.recent_topics}"
                ),
            },
        ]
    )
    parsed = parse_json_array(raw)
    queries = [str(item.get("query") or item.get("title") or "").strip() for item in parsed]
    queries = [q for q in queries if q]
    if queries:
        return queries[:limit]
    return fallback[:limit] or ctx.recent_topics[:limit]
