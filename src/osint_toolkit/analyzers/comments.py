"""评论分析 / Comment analysis."""

from __future__ import annotations

import asyncio

from osint_toolkit.ai.client import DeepSeekClient
from osint_toolkit.ai.steering import build_system_prompt, is_step_enabled


def select_top_comments(comments: list[dict], limit: int = 5) -> list[dict]:
    return sorted(comments, key=lambda c: c.get("likes", 0), reverse=True)[:limit]


async def summarize_comments(
    comments: list[dict],
    *,
    client: DeepSeekClient | None = None,
    no_ai: bool = False,
    disabled_steps: list[str] | None = None,
) -> str:
    top = select_top_comments(comments)
    if not top:
        return ""
    lines: list[str] = []
    for i, c in enumerate(top):
        lines.append(f"{i+1}. ({c.get('likes',0)}赞) {c.get('content','')}")
        replies = c.get("replies") or []
        if replies:
            for j, r in enumerate(replies[:3]):
                lines.append(f"   {i+1}.{j+1} (回复,{r.get('likes',0)}赞) {r.get('content','')}")
            if len(replies) > 3:
                lines.append(f"   ... 还有 {len(replies) - 3} 条回复未展示")
    if not is_step_enabled("comment_mine", no_ai=no_ai, disabled_steps=disabled_steps):
        return "社区评论精选:\n" + "\n".join(line.split(") ", 1)[-1] for line in lines if line.strip())
    prompt = "\n".join(lines)
    try:
        client = client or DeepSeekClient()
        result = await asyncio.to_thread(
            client.chat,
            messages=[
                {"role": "system", "content": build_system_prompt(task="评论归纳")},
                {"role": "user", "content": "请归纳以下评论（含回复）中的亲测、反驳、补充信息，标注为社区观点非事实。\n"
                 "严格遵守：仅基于提供的评论内容归纳，不得引入评论中不存在的信息。\n"
                 f"{prompt}"},
            ],
        )
        if not result or not result.strip():
            no_ai_fallback = [f"- {line.split(') ', 1)[-1]}" for line in lines if line.strip()]
            return "社区评论精选:\n" + "\n".join(no_ai_fallback)
        return result
    except Exception:  # noqa: BLE001
        no_ai_fallback = [f"- {line.split(') ', 1)[-1]}" for line in lines if line.strip()]
        return "社区评论精选:\n" + "\n".join(no_ai_fallback)
