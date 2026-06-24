"""AI 摘要 / AI summarization."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from osint_toolkit.ai.client import DeepSeekClient
from osint_toolkit.ai.prompt_loader import load_prompt
from osint_toolkit.ai.steering import build_system_prompt, directives_hash, is_step_enabled
from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.persona.context import PersonaContext


def _fallback_summary(item: IntelItem) -> str:
    text = item.content or item.title
    return text[:300] + ("..." if len(text) > 300 else "")


def summarize_item(
    item: IntelItem,
    *,
    client: DeepSeekClient | None = None,
    runtime_instruct: str = "",
    no_ai: bool = False,
    disabled_steps: list[str] | None = None,
    persona_ctx: PersonaContext | None = None,
) -> tuple[str, dict]:
    meta = {"prompt_source": "builtin", "directives_hash": directives_hash(), "ai_invoked": False}
    if not is_step_enabled("summarize", no_ai=no_ai, disabled_steps=disabled_steps):
        return _fallback_summary(item), meta
    prompt_tpl, source = load_prompt("summarize")
    meta["prompt_source"] = source
    meta["ai_invoked"] = True
    content = (item.content or item.title)[:6000]
    hints_block = ""
    if persona_ctx and persona_ctx.interest_hints:
        hints_block = f"\n近期关注: {json.dumps(persona_ctx.interest_hints[:5], ensure_ascii=False)}\n"
    comments_block = ""
    comments_summary = item.layers.get("comments_summary")
    if comments_summary:
        comments_block = f"\n\n社区观点（非事实，来自热评归纳）:\n{comments_summary[:2000]}\n"
    try:
        client = client or DeepSeekClient()
        summary = client.chat(
            messages=[
                {
                    "role": "system",
                    "content": build_system_prompt(
                        task="摘要",
                        runtime_instruct=runtime_instruct,
                        persona_brief=persona_ctx.brief if persona_ctx else "",
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"{prompt_tpl}{hints_block}\n\n标题:{item.title}\n来源:{item.source}\n\n{content}"
                        f"{comments_block}"
                    ),
                },
            ]
        )
    except Exception as exc:  # noqa: BLE001
        meta["ai_error"] = str(exc)
        return _fallback_summary(item), meta
    if not summary or not summary.strip() or len(summary.strip()) < 10:
        summary = _fallback_summary(item)
    item.summary = summary
    return summary, meta


def summarize_batch(
    items: list[IntelItem],
    *,
    client: DeepSeekClient | None = None,
    runtime_instruct: str = "",
    no_ai: bool = False,
    disabled_steps: list[str] | None = None,
    persona_ctx: PersonaContext | None = None,
    max_workers: int = 4,
) -> list[dict]:
    if not items:
        return []
    if no_ai or not is_step_enabled("summarize", no_ai=no_ai, disabled_steps=disabled_steps):
        return [
            {
                "id": item.id,
                "summary": _fallback_summary(item),
                "meta": {"prompt_source": "builtin", "directives_hash": directives_hash(), "ai_invoked": False},
            }
            for item in items
        ]

    try:
        shared_client = client or DeepSeekClient()
    except Exception:  # noqa: BLE001
        shared_client = None

    def _one(item: IntelItem) -> dict:
        summary, meta = summarize_item(
            item,
            client=shared_client,
            runtime_instruct=runtime_instruct,
            no_ai=no_ai,
            disabled_steps=disabled_steps,
            persona_ctx=persona_ctx,
        )
        return {"id": item.id, "summary": summary, "meta": meta}

    workers = max(1, min(max_workers, len(items)))
    if workers == 1:
        return [_one(item) for item in items]

    results: list[dict | None] = [None] * len(items)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_one, item): idx for idx, item in enumerate(items)}
        for future in as_completed(futures):
            idx = futures[future]
            results[idx] = future.result()
    return [r for r in results if r is not None]
