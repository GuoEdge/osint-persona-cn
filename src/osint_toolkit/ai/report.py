"""AI 情报报告 / Intelligence report generation."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from osint_toolkit.ai.client import DeepSeekClient
from osint_toolkit.ai.prompt_loader import load_prompt
from osint_toolkit.ai.steering import build_system_prompt, is_step_enabled
from osint_toolkit.analyzers.cluster import cluster_items
from osint_toolkit.models.intel_item import IntelItem


def _fallback_report(query: str, items: list[IntelItem], run_id: str) -> str:
    lines = [f"# 情报报告: {query}", "", "## 执行摘要", f"- 共采集 {len(items)} 条情报", ""]
    for item in items[:10]:
        lines.append(f"### [{item.source}] {item.title}")
        lines.append(f"- URL: {item.url}")
        lines.append(f"- 摘要: {item.summary or item.content[:200]}")
        if item.signals.fold_reason:
            lines.append(f"- 折叠原因: {item.signals.fold_reason}")
        lines.append("")
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
) -> str:
    if not is_step_enabled("report", no_ai=no_ai):
        return _fallback_report(query, items, run_id)
    client = client or DeepSeekClient()
    prompt_tpl, _ = load_prompt("report")
    clusters = cluster_items(items)
    payload = {
        "query": query,
        "clusters": [
            {
                "name": c["name"],
                "items": [
                    {
                        "title": i.title,
                        "url": i.url,
                        "summary": i.summary,
                        "signals": i.signals.model_dump(),
                    }
                    for i in c["items"]
                ],
            }
            for c in clusters
        ],
    }
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
                "content": f"{prompt_tpl}\n\n数据:\n{json.dumps(payload, ensure_ascii=False)[:12000]}",
            },
        ]
    )
    footer = (
        f"\n\n---\n生成时间: {datetime.now(UTC).isoformat()}\nrun_id: `{run_id}`\n"
        "说明: 本报告为AI归纳草稿，请结合 trace 逐步核验。"
    )
    return report + footer
