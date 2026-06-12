"""AI 摘要 / AI summarization."""

from __future__ import annotations

from osint_toolkit.ai.client import DeepSeekClient
from osint_toolkit.ai.prompt_loader import load_prompt
from osint_toolkit.ai.steering import build_system_prompt, directives_hash, is_step_enabled
from osint_toolkit.models.intel_item import IntelItem


def _fallback_summary(item: IntelItem) -> str:
    text = item.content or item.title
    return text[:300] + ("..." if len(text) > 300 else "")


def summarize_item(
    item: IntelItem,
    *,
    client: DeepSeekClient | None = None,
    runtime_instruct: str = "",
    no_ai: bool = False,
) -> tuple[str, dict]:
    meta = {"prompt_source": "builtin", "directives_hash": directives_hash(), "ai_invoked": False}
    if not is_step_enabled("summarize", no_ai=no_ai):
        return _fallback_summary(item), meta
    client = client or DeepSeekClient()
    prompt_tpl, source = load_prompt("summarize")
    meta["prompt_source"] = source
    meta["ai_invoked"] = True
    content = (item.content or item.title)[:6000]
    summary = client.chat(
        messages=[
            {"role": "system", "content": build_system_prompt(task="摘要", runtime_instruct=runtime_instruct)},
            {"role": "user", "content": f"{prompt_tpl}\n\n标题:{item.title}\n来源:{item.source}\n\n{content}"},
        ]
    )
    item.summary = summary
    return summary, meta


def summarize_batch(
    items: list[IntelItem],
    *,
    client: DeepSeekClient | None = None,
    runtime_instruct: str = "",
    no_ai: bool = False,
) -> list[dict]:
    results = []
    for item in items:
        summary, meta = summarize_item(
            item, client=client, runtime_instruct=runtime_instruct, no_ai=no_ai
        )
        results.append({"id": item.id, "summary": summary, "meta": meta})
    return results
