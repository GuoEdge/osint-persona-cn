"""评论分析 / Comment analysis."""

from __future__ import annotations

from osint_toolkit.ai.client import DeepSeekClient
from osint_toolkit.ai.steering import build_system_prompt, is_step_enabled


def select_top_comments(comments: list[dict], limit: int = 5) -> list[dict]:
    return sorted(comments, key=lambda c: c.get("likes", 0), reverse=True)[:limit]


async def summarize_comments(
    comments: list[dict],
    *,
    client: DeepSeekClient | None = None,
    no_ai: bool = False,
) -> str:
    top = select_top_comments(comments)
    if not top:
        return ""
    if not is_step_enabled("comment_mine", no_ai=no_ai):
        lines = [f"- {c.get('content','')[:120]}" for c in top]
        return "社区评论精选:\n" + "\n".join(lines)
    client = client or DeepSeekClient()
    prompt = "\n".join(f"{i+1}. ({c.get('likes',0)}赞) {c.get('content','')}" for i, c in enumerate(top))
    return client.chat(
        messages=[
            {"role": "system", "content": build_system_prompt(task="评论归纳")},
            {"role": "user", "content": f"请归纳以下评论中的亲测、反驳、补充信息，标注为社区观点非事实:\n{prompt}"},
        ]
    )
