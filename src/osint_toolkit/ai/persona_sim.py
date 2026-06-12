"""Persona 模拟判断 / Persona simulation."""

from __future__ import annotations

import json

from osint_toolkit.ai.client import DeepSeekClient
from osint_toolkit.ai.json_util import parse_json_array
from osint_toolkit.ai.prompt_loader import load_prompt
from osint_toolkit.ai.steering import build_system_prompt, is_step_enabled
from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.persona.behavior_signals import load_recent_interest_hints
from osint_toolkit.persona.store import load_persona_brief

PERSONA_SIM_JSON_HINT = (
    "严格只输出 JSON 数组，不要 Markdown。每个元素字段："
    "item_id(字符串), interest( interested|neutral|skip ), confidence(0-1), "
    "verdict(一句话，从用户视角会不会点开), reason(依据)。"
)


def simulate_items(
    items: list[IntelItem],
    *,
    client: DeepSeekClient | None = None,
    no_ai: bool = False,
    no_simulate: bool = False,
) -> list[dict]:
    if no_simulate or not is_step_enabled("persona_simulate", no_ai=no_ai):
        return []
    client = client or DeepSeekClient()
    prompt_tpl, _ = load_prompt("persona_sim")
    persona_brief = load_persona_brief()
    if not persona_brief.strip():
        persona_brief = "（尚无画像 brief，请基于标题与摘要做保守 neutral 判断）"
    interest_hints = load_recent_interest_hints(limit=10)
    hints_block = ""
    if interest_hints:
        hints_block = f"\n近期高关注行为（含高停留阅读）:\n{json.dumps(interest_hints, ensure_ascii=False)}\n"
    payload = [
        {
            "item_id": i.id,
            "title": i.title,
            "source": i.source,
            "summary": i.summary or i.content[:200],
        }
        for i in items[:15]
    ]
    raw = client.chat(
        messages=[
            {
                "role": "system",
                "content": build_system_prompt(task="画像兴趣模拟", persona_brief=persona_brief),
            },
            {
                "role": "user",
                "content": (
                    f"{prompt_tpl}\n{PERSONA_SIM_JSON_HINT}\n\n"
                    f"用户 persona brief:\n{persona_brief[:2000]}\n"
                    f"{hints_block}\n"
                    f"候选条目:\n{json.dumps(payload, ensure_ascii=False)}"
                ),
            },
        ]
    )
    parsed = parse_json_array(raw)
    if parsed:
        return parsed
    return [{"raw": raw}]
