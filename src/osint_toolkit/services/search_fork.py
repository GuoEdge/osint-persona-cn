"""搜罗分叉与研究辅助 / Search fork and research helpers."""

from __future__ import annotations

import json
from typing import Any

from osint_toolkit.auth.paths import get_data_dir
from osint_toolkit.feedback.store import FeedbackStore
from osint_toolkit.services.run_session import read_manifest, read_request
from osint_toolkit.services.search_params import SEARCH_SESSION_KEYS, pipeline_search_kwargs


def build_fork_search_params(fork_from_run_id: str, overrides: dict[str, Any]) -> dict[str, Any]:
    """从上一轮 run 继承 pipeline 参数，合并噪音排除与报告摘要到 ai_instruct。"""
    base = pipeline_search_kwargs(read_request(fork_from_run_id) or {})
    manifest = read_manifest(fork_from_run_id) or {}
    if not base.get("query") and manifest.get("query"):
        base["query"] = manifest["query"]

    run_dir = get_data_dir() / "runs" / fork_from_run_id
    report_path = run_dir / "report.md"
    report_snippet = ""
    if report_path.exists():
        report_snippet = report_path.read_text(encoding="utf-8")[:2500]

    noise_urls: list[str] = []
    useful_titles: list[str] = []
    store = FeedbackStore()
    items_path = None
    for name in ("items_dedup.json",):
        matches = list(run_dir.glob(f"*{name}"))
        if matches:
            items_path = matches[0]
            break
    if not items_path:
        matches = list(run_dir.glob("*items_dedup.json"))
        if matches:
            items_path = matches[0]
    item_by_id: dict[str, dict[str, Any]] = {}
    if items_path and items_path.exists():
        try:
            raw = json.loads(items_path.read_text(encoding="utf-8"))
            items = raw if isinstance(raw, list) else raw.get("items") or []
            for it in items:
                if isinstance(it, dict) and it.get("id"):
                    item_by_id[str(it["id"])] = it
        except json.JSONDecodeError:
            pass

    for entry in store.list_recent(limit=500):
        if entry.get("run_id") != fork_from_run_id:
            continue
        tid = str(entry.get("target_id") or "")
        rating = entry.get("rating")
        item = item_by_id.get(tid)
        if rating == "noise" and item and item.get("url"):
            noise_urls.append(str(item["url"]))
        if rating == "useful" and item and item.get("title"):
            useful_titles.append(str(item["title"])[:80])

    instruct_parts: list[str] = []
    prev_instruct = str(base.get("ai_instruct") or overrides.get("ai_instruct") or "").strip()
    if prev_instruct:
        instruct_parts.append(prev_instruct)
    if report_snippet:
        instruct_parts.append(f"上一轮情报报告摘要（供延续研究）：\n{report_snippet}")
    if useful_titles:
        instruct_parts.append("优先关注这些有用条目：" + "；".join(useful_titles[:8]))
    if noise_urls:
        instruct_parts.append("排除以下噪音 URL：" + "；".join(noise_urls[:12]))

    merged = {
        **base,
        **pipeline_search_kwargs({k: v for k, v in overrides.items() if v is not None}),
    }
    for key in SEARCH_SESSION_KEYS:
        val = overrides.get(key)
        if val is not None:
            merged[key] = val
    if instruct_parts:
        merged["ai_instruct"] = "\n\n".join(instruct_parts)[:8000]
    merged["fork_from_run_id"] = fork_from_run_id
    return merged
