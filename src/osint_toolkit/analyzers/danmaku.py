"""弹幕聚合 / Danmaku aggregation."""

from __future__ import annotations

from collections import Counter

from osint_toolkit.ai.client import DeepSeekClient
from osint_toolkit.ai.steering import build_system_prompt, is_step_enabled


def aggregate_danmaku(lines: list[str], top_n: int = 10) -> list[dict]:
    counter = Counter(line.strip() for line in lines if line.strip())
    return [{"text": text, "count": count} for text, count in counter.most_common(top_n)]


async def summarize_danmaku(top: list[dict], *, no_ai: bool = False) -> str:
    if not top:
        return ""
    if not is_step_enabled("danmaku_interpret", no_ai=no_ai):
        lines = [f"- ({row.get('count', 0)}次) {row.get('text', '')[:80]}" for row in top[:10]]
        return "弹幕高频片段:\n" + "\n".join(lines)
    client = DeepSeekClient()
    prompt = "\n".join(f"{i+1}. ({row.get('count', 0)}次) {row.get('text', '')}" for i, row in enumerate(top[:12]))
    return client.chat(
        messages=[
            {"role": "system", "content": build_system_prompt(task="弹幕归纳")},
            {
                "role": "user",
                "content": f"请归纳以下弹幕高频片段反映的观众情绪与关注点，标注为社区主观观点:\n{prompt}",
            },
        ]
    )
