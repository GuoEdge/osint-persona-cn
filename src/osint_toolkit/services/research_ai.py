"""研究 AI 辅助：要点归纳与搜罗建议。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from osint_toolkit.ai.client import DeepSeekClient
from osint_toolkit.ai.steering import build_system_prompt
from osint_toolkit.feedback.store import FeedbackStore
from osint_toolkit.persona.context import maybe_load_persona_context
from osint_toolkit.research.tree import add_node, load_tree, save_tree
from osint_toolkit.services.run_session import run_dir_for_read
from osint_toolkit.services.runs import show_run


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _useful_titles_for_run(run_id: str) -> list[str]:
    run_dir = run_dir_for_read(run_id)
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


def _run_item_titles(run_id: str, *, limit: int = 12) -> list[str]:
    run_dir = run_dir_for_read(run_id)
    titles: list[str] = []
    for path in run_dir.glob("*items_dedup.json"):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            items = raw if isinstance(raw, list) else raw.get("items") or []
            for it in items:
                if isinstance(it, dict) and it.get("title"):
                    titles.append(str(it["title"])[:100])
                if len(titles) >= limit:
                    return titles
        except json.JSONDecodeError:
            continue
    return titles


def _run_context(run_id: str) -> tuple[str, str, list[str]]:
    run_data = show_run(run_id)
    query = str(run_data.get("query") or "")
    report = str(run_data.get("report") or "")[:6000]
    useful = _useful_titles_for_run(run_id)
    if not report:
        titles = useful or _run_item_titles(run_id)
        report = "（未生成情报报告）\n条目摘要:\n" + "\n".join(f"- {t}" for t in titles[:12])
    return query, report, useful


def _persona_prompt_block() -> str:
    ctx = maybe_load_persona_context()
    if not ctx:
        return ""
    parts: list[str] = []
    if ctx.brief:
        parts.append(f"用户画像:\n{ctx.brief}")
    if ctx.interest_hints:
        hints = json.dumps(ctx.interest_hints[:8], ensure_ascii=False)
        parts.append(f"近期兴趣:\n{hints}")
    return "\n\n".join(parts)


def generate_insight(*, tree_id: str, run_id: str, parent_node_id: str | None = None) -> dict[str, Any]:
    try:
        query, report, useful = _run_context(run_id)
    except FileNotFoundError as exc:
        return {"ok": False, "error": str(exc)}
    context = f"话题: {query}\n报告:\n{report}\n有用条目: {', '.join(useful)}"
    persona_block = _persona_prompt_block()
    if persona_block:
        context = f"{persona_block}\n\n{context}"
    try:
        client = DeepSeekClient()
        persona_ctx = maybe_load_persona_context()
        text = client.chat(
            messages=[
                {
                    "role": "system",
                    "content": build_system_prompt(
                        task="归纳本轮搜罗要点",
                        persona_brief=persona_ctx.brief if persona_ctx else "",
                    )
                    + " 用 3-6 条要点归纳本轮搜罗收获，每条一行，简洁可执行。",
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
            base_query, report, _ = _run_context(run_id)
            report = report[:4000]
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
    persona_block = _persona_prompt_block()
    user_content = f"原话题:{base_query}\n报告摘要:{report[:2000]}"
    if persona_block:
        user_content = f"{persona_block}\n\n{user_content}"
    try:
        client = DeepSeekClient()
        persona_ctx = maybe_load_persona_context()
        raw = client.chat(
            messages=[
                {
                    "role": "system",
                    "content": build_system_prompt(
                        task="后续搜罗建议",
                        persona_brief=persona_ctx.brief if persona_ctx else "",
                    )
                    + " 输出 1-3 个后续搜罗查询词，JSON 数组字符串，不要其它文字。",
                },
                {
                    "role": "user",
                    "content": user_content,
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
    if tree_id and queries:
        try:
            tree = load_tree(tree_id)
            tree.setdefault("meta", {})["suggested_queries"] = queries
            tree["meta"]["suggested_queries_at"] = _now_iso()
            save_tree(tree)
        except Exception:  # noqa: BLE001
            pass
    return {"ok": True, "queries": queries}


def summarize_tree(tree_id: str) -> dict[str, Any]:
    """对整棵研究树做跨轮次 AI 综合归纳，生成根级 insight 节点。"""
    try:
        tree = load_tree(tree_id)
    except FileNotFoundError as exc:
        return {"ok": False, "error": str(exc)}
    insights = [n["payload"] for n in tree.get("nodes") or [] if n.get("kind") == "insight" and n.get("payload")]
    search_titles = [n["title"] for n in tree.get("nodes") or [] if n.get("kind") == "search"]
    if not insights and not search_titles:
        return {"ok": False, "error": "研究树暂无搜罗或要点可归纳"}
    context_parts = [f"研究主题: {tree.get('title', '')}"]
    if search_titles:
        context_parts.append("已完成的搜罗轮次:\n" + "\n".join(f"- {t}" for t in search_titles))
    if insights:
        context_parts.append("已有要点归纳:\n" + "\n".join(p[:500] for p in insights[:10]))
    context = "\n\n".join(context_parts)
    persona_block = _persona_prompt_block()
    if persona_block:
        context = f"{persona_block}\n\n{context}"
    try:
        client = DeepSeekClient()
        persona_ctx = maybe_load_persona_context()
        text = client.chat(
            messages=[
                {
                    "role": "system",
                    "content": build_system_prompt(
                        task="研究树全貌归纳",
                        persona_brief=persona_ctx.brief if persona_ctx else "",
                    )
                    + " 综合多轮搜罗结果，给出 3-6 条跨轮次核心发现。每条一行，简洁可执行。",
                },
                {"role": "user", "content": context},
            ]
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
    root_id = tree["nodes"][0]["id"] if tree.get("nodes") else None
    node = add_node(
        tree_id,
        parent_id=root_id,
        kind="insight",
        title="全树归纳",
        payload=text.strip(),
        meta={"type": "tree_summary"},
    )
    return {"ok": True, "node": node, "insight": text.strip()}
