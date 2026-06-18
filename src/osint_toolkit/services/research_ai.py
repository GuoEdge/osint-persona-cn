"""研究 AI 辅助：要点归纳与搜罗建议。"""

from __future__ import annotations

import json
from typing import Any

from osint_toolkit.ai.client import DeepSeekClient
from osint_toolkit.auth.paths import get_data_dir
from osint_toolkit.feedback.store import FeedbackStore
from osint_toolkit.research.tree import add_node, load_tree
from osint_toolkit.services.runs import show_run


def _useful_titles_for_run(run_id: str) -> list[str]:
    run_dir = get_data_dir() / "runs" / run_id
    item_by_id: dict[str, dict[str, Any]] = {}
    for path in run_dir.glob("*items_dedup.json"):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            items = raw if isinstance(raw, list) else raw.get("items") or []
            for it in items:
                if isinstance(it, dict) and it.get("id"):
                    item_by_id[str(it["id"])] = it
        except json.JSONDecodeError:
            continue
    titles: list[str] = []
    for entry in FeedbackStore().list_recent(limit=2000):
        if entry.get("run_id") != run_id or entry.get("rating") != "useful":
            continue
        item = item_by_id.get(str(entry.get("target_id") or ""))
        if item and item.get("title"):
            titles.append(str(item["title"])[:100])
    return titles[:10]


def generate_insight(*, tree_id: str, run_id: str, parent_node_id: str | None = None) -> dict[str, Any]:
    try:
        run_data = show_run(run_id)
    except FileNotFoundError as exc:
        return {"ok": False, "error": str(exc)}
    report = str(run_data.get("report") or "")[:6000]
    useful = _useful_titles_for_run(run_id)
    context = f"话题: {run_data.get('query', '')}\n报告:\n{report}\n有用条目: {', '.join(useful)}"
    try:
        client = DeepSeekClient()
        text = client.chat(
            messages=[
                {
                    "role": "system",
                    "content": "你是情报研究助手。用 3-6 条要点归纳本轮搜罗收获，每条一行，简洁可执行。",
                },
                {"role": "user", "content": context},
            ]
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    node = add_node(
        tree_id,
        parent_id=parent_node_id or _search_node_id(tree_id, run_id),
        kind="insight",
        title="研究要点",
        payload=text.strip(),
        meta={"run_id": run_id},
    )
    return {"ok": True, "node": node, "insight": text.strip()}


def _search_node_id(tree_id: str, run_id: str) -> str | None:
    try:
        data = load_tree(tree_id)
    except FileNotFoundError:
        return None
    for node in data.get("nodes") or []:
        if node.get("run_id") == run_id:
            return node.get("id")
    return None


def suggest_queries(*, run_id: str | None = None, tree_id: str | None = None) -> dict[str, Any]:
    base_query = ""
    report = ""
    if run_id:
        try:
            run_data = show_run(run_id)
            base_query = str(run_data.get("query") or "")
            report = str(run_data.get("report") or "")[:4000]
        except FileNotFoundError:
            pass
    if tree_id and not base_query:
        try:
            t = load_tree(tree_id)
            base_query = str(t.get("title") or "")
        except FileNotFoundError:
            pass
    if not base_query and not report:
        return {"ok": False, "error": "需要 run_id 或 tree_id", "queries": []}
    try:
        client = DeepSeekClient()
        raw = client.chat(
            messages=[
                {
                    "role": "system",
                    "content": "输出 1-3 个后续搜罗查询词，JSON 数组字符串，不要其它文字。",
                },
                {
                    "role": "user",
                    "content": f"原话题:{base_query}\n报告摘要:{report[:2000]}",
                },
            ]
        )
        queries = json.loads(raw.strip())
        if isinstance(queries, list):
            queries = [str(q) for q in queries[:3]]
        else:
            queries = []
    except Exception:  # noqa: BLE001
        queries = [f"{base_query} 深度分析", f"{base_query} 实践案例"] if base_query else []
    return {"ok": True, "queries": queries}
