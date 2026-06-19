"""Persona 构建 / Persona builder."""

from __future__ import annotations

import json
import logging
import shutil
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from osint_toolkit.ai.client import DeepSeekClient
from osint_toolkit.feedback.store import FeedbackStore
from osint_toolkit.persona.behavior_signals import (
    INVENTORY_SNAPSHOT_TYPES,
    load_event_type_breakdown,
    load_ranked_behavior_samples,
    load_recent_interest_hints,
)
from osint_toolkit.persona.context import mark_persona_built
from osint_toolkit.persona.store import (
    load_mental_model,
    load_persona_brief,
    mental_model_path,
    persona_dir,
    save_mental_model,
    save_persona_brief,
)
from osint_toolkit.storage.sqlite import connect

logger = logging.getLogger(__name__)

_SOURCE_LABELS = {
    "bilibili": "B站",
    "zhihu": "知乎",
    "github": "GitHub",
    "web": "网页",
    "extension": "扩展",
    "weixin": "微信",
    "v2ex": "V2EX",
}


def _format_fallback_brief(
    sources: Counter,
    interest_hints: list[dict[str, Any]],
    *,
    feedback_count: int,
    event_breakdown: dict[str, Any] | None = None,
    ai_error: str | None = None,
) -> str:
    """无 AI 或 AI 失败时的可读摘要（Markdown）。"""
    src_bits = [
        f"{_SOURCE_LABELS.get(k, k)} {v}条"
        for k, v in sorted(sources.items(), key=lambda x: -x[1])
    ]
    lines = [
        "## 关注概况",
        f"近期行为主要来自：{'、'.join(src_bits) or '暂无'}。",
        f"搜罗反馈 **{feedback_count}** 条。",
    ]
    if event_breakdown:
        recent_7d = event_breakdown.get("recent_activity_7d") or {}
        if recent_7d:
            bits = [f"{k} {v}条" for k, v in sorted(recent_7d.items(), key=lambda x: -x[1])[:6]]
            lines.append(f"近 7 日活跃信号：{'、'.join(bits)}。")
        inv = event_breakdown.get("inventory_snapshots") or {}
        if inv:
            inv_total = sum(inv.values())
            lines.append(
                f"（账号清单同步 {inv_total} 条收藏/关注快照不计入近期高频行为。）"
            )
    titles = [str(h.get("title") or "").strip() for h in interest_hints if h.get("title")]
    if titles:
        lines.extend(["", "## 高兴趣内容（停留/浏览/赞同）"])
        for title in titles[:10]:
            lines.append(f"- {title[:100]}")
    if ai_error:
        lines.extend(
            [
                "",
                f"> AI 叙事摘要未生成：{ai_error}",
                "> 请在设置页确认 DeepSeek API Key 后，点击「构建画像」重试。",
            ]
        )
    else:
        lines.extend(["", "> 此为规则摘要。配置 DeepSeek API Key 后「构建画像」可生成更完整的 AI 叙事。"])
    return "\n".join(lines)


def _archive_model_version(version: int) -> None:
    if version < 1:
        return
    src = mental_model_path()
    if not src.exists():
        return
    dst = persona_dir() / f"mental_model.v{version}.yaml"
    if not dst.exists():
        shutil.copy2(src, dst)


def _archive_brief_version(version: int) -> None:
    from osint_toolkit.persona.store import archive_brief_version

    archive_brief_version(version)


def build_persona_draft(
    *,
    use_ai: bool = True,
    event_limit: int = 500,
    feedback_limit: int = 500,
    review: bool = False,
) -> dict[str, Any]:
    old_brief = load_persona_brief()
    old_hints = load_recent_interest_hints(limit=8)
    conn = connect()
    rows = conn.execute(
        "SELECT event_type, data_json FROM events ORDER BY id DESC LIMIT ?",
        (event_limit,),
    ).fetchall()
    conn.close()
    all_feedback = FeedbackStore().list_recent(feedback_limit)
    feedback = all_feedback
    sim_feedback = [f for f in all_feedback if f.get("target_type") == "simulation"]
    sources = Counter()
    event_types = Counter()
    for row in rows:
        data = json.loads(row["data_json"])
        sources[data.get("source", "unknown")] += 1
        event_types[row["event_type"]] += 1
    ranked_sample = load_ranked_behavior_samples(fetch_limit=event_limit, sample_limit=40)
    interest_hints = load_recent_interest_hints(limit=15)
    event_breakdown = load_event_type_breakdown(fetch_limit=event_limit)
    model = load_mental_model()
    old_version = int(model.get("version", 1))
    _archive_model_version(old_version)
    _archive_brief_version(old_version)
    model["version"] = old_version + 1
    model["built_at"] = datetime.now(UTC).isoformat()
    model["recent_sources"] = dict(sources)
    model["recent_event_types"] = dict(event_types)
    model["inventory_snapshot_types"] = list(INVENTORY_SNAPSHOT_TYPES)
    model["event_breakdown"] = event_breakdown
    model["feedback_count"] = len(feedback)
    model["sim_feedback_count"] = len(sim_feedback)
    model["sample_size"] = {"events": len(rows), "feedback": len(feedback)}
    model["high_interest_hints"] = interest_hints
    save_mental_model(model)
    _archive_model_version(int(model["version"]))
    ai_error: str | None = None
    brief = _format_fallback_brief(
        sources, interest_hints, feedback_count=len(feedback), event_breakdown=event_breakdown
    )
    if use_ai:
        try:
            client = DeepSeekClient()
            brief = client.chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "根据用户行为数据生成简短 persona brief（中文 Markdown），供搜罗模拟与 AI 注入使用。"
                            "优先依据：页面停留(ext_page_dwell)、浏览(zhihu_browse/bilibili_watch)、"
                            "赞同(zhihu_vote)、发布(zhihu_pin/zhihu_answer)、扩展被动采集。"
                            "inventory_snapshots（bilibili_follow/bilibili_fav/zhihu_fav/zhihu_follow）"
                            "是账号全量清单同步，仅反映长期偏好库，禁止解读为「近期高频率收藏与关注」。"
                            "列出 3-6 个兴趣领域与一句话总结。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": str(
                            {
                                "sources": dict(sources),
                                "event_types": dict(event_types),
                                "event_breakdown": event_breakdown,
                                "feedback": feedback[:100],
                                "simulation_feedback": sim_feedback[:50],
                                "ranked_behavior_sample": ranked_sample,
                                "high_interest_hints": interest_hints,
                            }
                        )[:12000],
                    },
                ]
            ).strip()
            if not brief:
                ai_error = "AI 返回空内容"
                brief = _format_fallback_brief(
                    sources,
                    interest_hints,
                    feedback_count=len(feedback),
                    event_breakdown=event_breakdown,
                    ai_error=ai_error,
                )
            else:
                model["brief_ai_generated"] = True
                model.pop("brief_ai_error", None)
        except Exception as exc:  # noqa: BLE001
            ai_error = str(exc)
            logger.warning("persona brief AI failed: %s", exc)
            brief = _format_fallback_brief(
                sources,
                interest_hints,
                feedback_count=len(feedback),
                event_breakdown=event_breakdown,
                ai_error=ai_error,
            )
            model["brief_ai_generated"] = False
            model["brief_ai_error"] = ai_error[:500]
    else:
        model["brief_ai_generated"] = False
        model.pop("brief_ai_error", None)
    save_mental_model(model)
    save_persona_brief(brief)
    _archive_brief_version(int(model["version"]))
    mark_persona_built()
    from osint_toolkit.persona.auto_rebuild import set_pending_rebuild_flag

    set_pending_rebuild_flag(False)
    result: dict[str, Any] = {"mental_model": model, "persona_brief": brief}
    if ai_error:
        result["brief_ai_error"] = ai_error
    if review:
        result["review_summary"] = {
            "brief_before": old_brief[:800],
            "brief_after": brief[:800],
            "interest_hints_before": old_hints,
            "interest_hints_after": interest_hints[:8],
        }
    return result
