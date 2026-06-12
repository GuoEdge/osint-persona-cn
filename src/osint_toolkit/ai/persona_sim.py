"""Persona 模拟判断 / Persona simulation."""

from __future__ import annotations

import json

from osint_toolkit.ai.client import DeepSeekClient
from osint_toolkit.ai.prompt_loader import load_prompt
from osint_toolkit.ai.steering import build_system_prompt, is_step_enabled
from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.persona.store import load_persona_brief


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
    payload = [
        {"id": i.id, "title": i.title, "source": i.source, "summary": i.summary or i.content[:200]}
        for i in items[:15]
    ]
    raw = client.chat(
        messages=[
            {
                "role": "system",
                "content": build_system_prompt(task="模拟判断", persona_brief=persona_brief),
            },
            {"role": "user", "content": f"{prompt_tpl}\n\n{json.dumps(payload, ensure_ascii=False)}"},
        ]
    )
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return [{"raw": raw}]
