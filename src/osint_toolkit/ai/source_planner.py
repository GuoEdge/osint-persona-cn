"""AI 链式信源规划 / Chain-of-thought source planning."""

from __future__ import annotations

import json
from typing import Any

from osint_toolkit.ai.client import DeepSeekClient
from osint_toolkit.ai.json_util import parse_json_object
from osint_toolkit.ai.prompt_loader import load_prompt
from osint_toolkit.ai.steering import build_system_prompt, is_step_enabled
from osint_toolkit.collectors.registry import COLLECTORS
from osint_toolkit.collectors.source_catalog import get_source_entries, get_source_labels
from osint_toolkit.persona.context import PersonaContext
from osint_toolkit.utils.config import get_search_config

_EMPTY_PLAN: dict[str, Any] = {
    "reasoning_chain": [],
    "topic_keywords": [],
    "topic_summary": "",
    "is_cryptic": False,
    "source_scores": {},
    "ai_invoked": False,
}


def _empty_plan(*, note: str = "") -> dict[str, Any]:
    out = dict(_EMPTY_PLAN)
    if note:
        out["reasoning_chain"] = [
            {"id": "skipped", "title": "未调用 AI", "content": note},
        ]
    return out


def _catalog_for_prompt() -> str:
    lines: list[str] = []
    for entry in get_source_entries():
        sid = str(entry.get("id") or "")
        if sid not in COLLECTORS:
            continue
        label = str(entry.get("label") or sid)
        desc = str(entry.get("description") or "")
        lines.append(f"- {sid}: {label} — {desc}")
    return "\n".join(lines)


def _normalize_plan(raw: dict[str, Any]) -> dict[str, Any]:
    chain = raw.get("reasoning_chain") or []
    if isinstance(chain, dict):
        chain = [chain]
    norm_chain: list[dict[str, str]] = []
    for i, step in enumerate(chain):
        if not isinstance(step, dict):
            continue
        norm_chain.append(
            {
                "id": str(step.get("id") or f"step_{i + 1}"),
                "title": str(step.get("title") or f"步骤 {i + 1}"),
                "content": str(step.get("content") or "").strip(),
            }
        )

    keywords = raw.get("topic_keywords") or []
    if isinstance(keywords, str):
        keywords = [keywords]
    keywords = [str(k).strip() for k in keywords if str(k).strip()]

    scores_in = raw.get("source_scores") or {}
    norm_scores: dict[str, dict[str, Any]] = {}
    if isinstance(scores_in, dict):
        for sid, val in scores_in.items():
            key = str(sid).strip()
            if key not in COLLECTORS:
                continue
            if isinstance(val, (int, float)):
                score = max(0, min(100, float(val)))
                norm_scores[key] = {"score": score, "tier": _tier_from_score(score), "reason": ""}
            elif isinstance(val, dict):
                try:
                    score = max(0, min(100, float(val.get("score") or 0)))
                except (TypeError, ValueError):
                    score = 0.0
                tier = str(val.get("tier") or _tier_from_score(score))
                norm_scores[key] = {
                    "score": score,
                    "tier": tier,
                    "reason": str(val.get("reason") or "").strip(),
                }

    return {
        "reasoning_chain": norm_chain,
        "topic_keywords": keywords,
        "topic_summary": str(raw.get("topic_summary") or "").strip(),
        "is_cryptic": bool(raw.get("is_cryptic")),
        "source_scores": norm_scores,
        "ai_invoked": True,
    }


def _tier_from_score(score: float) -> str:
    if score >= 70:
        return "strong"
    if score >= 40:
        return "medium"
    if score >= 15:
        return "weak"
    return "skip"


def detect_cryptic_query(query: str, rule_scores: dict[str, float]) -> bool:
    """规则分普遍偏低时视为隐晦查询，提高 AI 权重。"""
    cfg = get_search_config().get("source_auto_route") or {}
    threshold = float(cfg.get("cryptic_rule_max", 35))
    if not rule_scores:
        return len((query or "").strip()) >= 2
    return max(rule_scores.values()) < threshold


def plan_sources(
    query: str,
    user_sources: list[str],
    *,
    persona_ctx: PersonaContext | None = None,
    rule_scores: dict[str, float] | None = None,
    query_intent: str = "",
    expanded_queries: list[str] | None = None,
    is_cryptic_hint: bool = False,
    no_ai: bool = False,
    disabled_steps: list[str] | None = None,
) -> dict[str, Any]:
    """DeepSeek 链式分析话题关键词与各信源相关度。"""
    if no_ai or not is_step_enabled("source_plan", no_ai=no_ai, disabled_steps=disabled_steps):
        return _empty_plan(note="已跳过 AI 信源规划（无 AI 或步骤已禁用）。")

    rule_scores = rule_scores or {}
    top_rule = sorted(
        [(s, sc) for s, sc in rule_scores.items() if sc > 0],
        key=lambda x: -x[1],
    )[:8]

    client = DeepSeekClient()
    prompt_tpl, _ = load_prompt("source_plan")
    brief = (persona_ctx.brief if persona_ctx else "")[:1200]
    hints = persona_ctx.interest_hints[:5] if persona_ctx else []

    user_msg = (
        f"{prompt_tpl}\n\n"
        f"## 用户查询\n{query}\n\n"
        f"## 意图摘要\n{query_intent or query}\n\n"
        f"## 用户勾选信源\n{json.dumps(user_sources, ensure_ascii=False)}\n\n"
        f"## 扩展查询词\n{json.dumps(expanded_queries or [query], ensure_ascii=False)}\n\n"
        f"## 规则引擎先验分（0-100，供参考）\n"
        f"{json.dumps(top_rule, ensure_ascii=False)}\n\n"
        f"## 是否疑似隐晦查询\n{json.dumps(is_cryptic_hint, ensure_ascii=False)}\n\n"
        f"## 心智画像摘要\n{brief}\n\n"
        f"## 近期兴趣\n{json.dumps(hints, ensure_ascii=False)}\n\n"
        f"## 可选信源目录\n{_catalog_for_prompt()}\n\n"
        "请按提示完成链式思考并输出 JSON。"
    )

    try:
        raw = client.chat(
            messages=[
                {
                    "role": "system",
                    "content": build_system_prompt(task="信源规划", persona_brief=brief),
                },
                {"role": "user", "content": user_msg},
            ],
            temperature=0.35,
        )
    except Exception as exc:  # noqa: BLE001
        return _empty_plan(note=f"AI 信源规划失败，已回退规则引擎：{exc}")

    parsed = parse_json_object(raw)
    if not parsed:
        return _empty_plan(note="AI 信源规划返回无法解析，已回退规则引擎。")

    plan = _normalize_plan(parsed)
    if is_cryptic_hint and not plan.get("is_cryptic"):
        plan["is_cryptic"] = True
    return plan


def extract_ai_score_map(plan: dict[str, Any] | None) -> dict[str, float]:
    out: dict[str, float] = {}
    for sid, meta in (plan or {}).get("source_scores", {}).items():
        if isinstance(meta, dict):
            out[str(sid)] = float(meta.get("score") or 0)
    return out
