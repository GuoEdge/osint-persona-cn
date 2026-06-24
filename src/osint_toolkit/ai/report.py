"""AI 情报报告 / Intelligence report generation."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime

from osint_toolkit.ai.client import DeepSeekClient
from osint_toolkit.ai.prompt_loader import load_prompt
from osint_toolkit.ai.steering import build_system_prompt, is_step_enabled
from osint_toolkit.analyzers.citations import citation_id_for_item
from osint_toolkit.analyzers.cluster import cluster_items
from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.utils.zhihu_urls import public_zhihu_url

_REPORT_PAYLOAD_CHARS = 24000


def _source_label(name: str) -> str:
    labels = {
        "zhihu": "知乎",
        "bilibili": "B站",
        "web": "网页",
        "weixin": "搜狗微信公众平台",
        "v2ex": "V2EX",
        "rss": "RSS",
        "ithome": "IT之家",
    }
    return labels.get(name, name)


def _item_report_row(item: IntelItem) -> dict:
    sig = item.signals.model_dump() if item.signals else {}
    cid = citation_id_for_item(item)
    return {
        "citation_id": cid,
        "title": item.title,
        "url": public_zhihu_url(item.url) if item.source == "zhihu" else item.url,
        "source": item.source,
        "source_label": _source_label(item.source),
        "summary": (item.summary or item.content or "")[:1200],
        "comments_summary": (item.layers.get("comments_summary") or "")[:800],
        "relevance": sig.get("relevance"),
        "fold_reason": sig.get("fold_reason") or "",
        "matched_queries": list(item.personal.get("matched_queries") or []),
        "metrics": item.metrics.model_dump() if item.metrics else {},
    }


def _build_report_payload(query: str, items: list[IntelItem]) -> dict:
    clusters = cluster_items(items)
    by_source = Counter(i.source for i in items)
    ranked = sorted(
        items,
        key=lambda i: float(getattr(getattr(i, "signals", None), "relevance", 0) or 0),
        reverse=True,
    )
    folded = [i for i in items if getattr(getattr(i, "signals", None), "fold_reason", None)]
    return {
        "query": query,
        "citation_instruction": (
            "引用条目时请使用 [cN] 格式（N 为 citation_id 数字部分，如 [c1]、[c2]），"
            "以便读者跳转到对应情报卡片。"
        ),
        "stats": {
            "total": len(items),
            "by_source": {_source_label(k): v for k, v in by_source.items()},
            "folded_count": len(folded),
        },
        "top_stories": [_item_report_row(i) for i in ranked[:18]],
        "folded_samples": [_item_report_row(i) for i in folded[:6]],
        "clusters": [
            {
                "name": _source_label(str(c["name"])),
                "count": c["count"],
                "items": [_item_report_row(i) for i in c["items"][:8]],
            }
            for c in clusters
        ],
    }


def _fallback_report(query: str, items: list[IntelItem], run_id: str) -> str:
    payload = _build_report_payload(query, items)
    lines = [
        f"# 情报报告: {query}",
        "",
        "## 执行摘要",
        f"- 共采集 {payload['stats']['total']} 条情报",
        f"- 信源分布: {payload['stats']['by_source']}",
        "",
        "## 阅读清单",
    ]
    for row in payload["top_stories"][:10]:
        cid = row.get("citation_id") or ""
        prefix = f"[{cid}] " if cid else ""
        lines.append(f"- {prefix}**[{row['source_label']}] {row['title']}** — {row['summary'][:160]}…")
        lines.append(f"  - {row['url']}")
    lines.append(f"\n---\nrun_id: `{run_id}`")
    return "\n".join(lines)


def generate_report(
    query: str,
    items: list[IntelItem],
    *,
    run_id: str,
    client: DeepSeekClient | None = None,
    runtime_instruct: str = "",
    no_ai: bool = False,
    persona_brief: str = "",
    disabled_steps: list[str] | None = None,
) -> str:
    if not is_step_enabled("report", no_ai=no_ai, disabled_steps=disabled_steps):
        return _fallback_report(query, items, run_id)
    prompt_tpl, _ = load_prompt("report")
    payload = _build_report_payload(query, items)
    try:
        client = client or DeepSeekClient()
        report = client.chat(
            messages=[
                {
                    "role": "system",
                    "content": build_system_prompt(
                        task="情报报告", runtime_instruct=runtime_instruct, persona_brief=persona_brief
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"{prompt_tpl}\n\n"
                        "写作要求：正文引用具体条目时使用 [cN] 格式（N 对应数据中 citation_id，如 c1、c2），"
                        "便于读者核验来源。\n\n"
                        f"数据:\n{json.dumps(payload, ensure_ascii=False)[:_REPORT_PAYLOAD_CHARS]}"
                    ),
                },
            ]
        )
    except Exception as exc:  # noqa: BLE001
        base = _fallback_report(query, items, run_id)
        return base + f"\n\n(AI 报告生成失败，已回退规则摘要: {exc})"
    if not report or not report.strip():
        return _fallback_report(query, items, run_id) + "\n\n(AI 报告返回空内容，已回退规则摘要)"
    footer = (
        f"\n\n---\n生成时间: {datetime.now(UTC).isoformat()}\nrun_id: `{run_id}`\n"
        "说明: 本报告为AI归纳草稿，请结合 trace 逐步核验。"
    )
    return report + footer
