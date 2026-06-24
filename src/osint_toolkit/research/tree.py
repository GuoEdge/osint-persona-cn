"""研究树存储 / Research tree persistence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from osint_toolkit.auth.paths import get_data_dir
from osint_toolkit.utils.atomic_write import atomic_write_text
from osint_toolkit.utils.safe_path import assert_safe_id, resolve_under

NODE_KINDS = frozenset({"topic", "search", "note", "insight", "ask"})


def _trees_dir() -> Any:
    path = get_data_dir() / "research" / "trees"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _tree_path(tree_id: str):
    safe_id = assert_safe_id(tree_id, label="tree_id")
    return resolve_under(_trees_dir(), f"{safe_id}.json")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_id() -> str:
    return uuid4().hex[:12]


def _atomic_write_text(path, text: str) -> None:
    """原子写入文本：先写临时文件再 os.replace，避免中途崩溃产生截断 JSON。"""
    atomic_write_text(path, text)


def create_tree(title: str, *, query: str = "") -> dict[str, Any]:
    tree_id = datetime.now(UTC).strftime("%Y%m%d") + f"-{_new_id()}"
    root_id = _new_id()
    tree = {
        "id": tree_id,
        "title": title,
        "created_at": _now(),
        "updated_at": _now(),
        "nodes": [
            {
                "id": root_id,
                "parent_id": None,
                "kind": "topic",
                "title": title,
                "run_id": None,
                "payload": query or title,
                "meta": {},
                "created_at": _now(),
            }
        ],
    }
    _atomic_write_text(_tree_path(tree_id), json.dumps(tree, ensure_ascii=False, indent=2))
    return tree


def list_trees(limit: int = 30) -> list[dict[str, Any]]:
    paths = sorted(_trees_dir().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    out: list[dict[str, Any]] = []
    for path in paths[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        out.append(
            {
                "id": data.get("id"),
                "title": data.get("title"),
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
                "node_count": len(data.get("nodes") or []),
            }
        )
    return out


def load_tree(tree_id: str) -> dict[str, Any]:
    path = _tree_path(tree_id)
    if not path.exists():
        raise FileNotFoundError(f"tree not found: {tree_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_tree(tree: dict[str, Any], *, expected_updated_at: str | None = None) -> None:
    """保存研究树。

    Args:
        expected_updated_at: 乐观并发控制——若传入且与磁盘上当前树的
            ``updated_at`` 不一致则抛 ``FileNotFoundError`` 表示已被其它写入
            覆盖，调用方应重新 ``load_tree`` 合并后再保存。
    """
    path = _tree_path(tree["id"])
    if expected_updated_at is not None and path.exists():
        try:
            disk = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            disk = {}
        if (disk.get("updated_at") or "") != expected_updated_at:
            raise FileNotFoundError(f"tree {tree['id']} was modified concurrently")
    tree["updated_at"] = _now()
    _atomic_write_text(path, json.dumps(tree, ensure_ascii=False, indent=2))


def _find_node(tree: dict[str, Any], node_id: str) -> dict[str, Any] | None:
    for node in tree.get("nodes") or []:
        if node.get("id") == node_id:
            return node
    return None


def add_node(
    tree_id: str,
    *,
    parent_id: str | None,
    kind: str,
    title: str,
    run_id: str | None = None,
    payload: str = "",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if kind not in NODE_KINDS:
        raise ValueError(f"invalid kind: {kind}")
    tree = load_tree(tree_id)
    if parent_id and not _find_node(tree, parent_id):
        raise ValueError(f"parent not found: {parent_id}")
    node = {
        "id": _new_id(),
        "parent_id": parent_id,
        "kind": kind,
        "title": title,
        "run_id": run_id,
        "payload": payload,
        "meta": meta or {},
        "created_at": _now(),
    }
    tree.setdefault("nodes", []).append(node)
    save_tree(tree)
    return node


def patch_node(tree_id: str, node_id: str, **fields: Any) -> dict[str, Any]:
    tree = load_tree(tree_id)
    node = _find_node(tree, node_id)
    if not node:
        raise ValueError(f"node not found: {node_id}")
    for key in ("title", "payload", "run_id", "meta"):
        if key in fields and fields[key] is not None:
            if key == "meta" and isinstance(fields[key], dict):
                node["meta"] = {**(node.get("meta") or {}), **fields[key]}
            else:
                node[key] = fields[key]
    save_tree(tree)
    return node


def attach_search_node(
    tree_id: str,
    *,
    parent_node_id: str | None,
    run_id: str,
    query: str,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return add_node(
        tree_id,
        parent_id=parent_node_id,
        kind="search",
        title=query,
        run_id=run_id,
        meta={"status": "running", "query": query, **(meta or {})},
    )


def find_search_node_id_for_run(tree_id: str, run_id: str) -> str | None:
    try:
        data = load_tree(tree_id)
    except FileNotFoundError:
        return None
    for node in data.get("nodes") or []:
        if node.get("kind") == "search" and node.get("run_id") == run_id:
            return node.get("id")
    return None


def update_search_node_status(tree_id: str, run_id: str, *, status: str) -> None:
    try:
        tree = load_tree(tree_id)
    except FileNotFoundError:
        return
    for node in tree.get("nodes") or []:
        if node.get("run_id") == run_id and node.get("kind") == "search":
            node.setdefault("meta", {})["status"] = status
            save_tree(tree)
            return


def mark_broken_run_for_trees(run_id: str) -> int:
    """Mark research tree search nodes referencing run_id as broken."""
    trees_dir = _trees_dir()
    updated = 0
    for path in trees_dir.glob("*.json"):
        try:
            tree = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        changed = False
        for node in tree.get("nodes") or []:
            if node.get("run_id") == run_id:
                node.setdefault("meta", {})["broken_run"] = True
                changed = True
        if changed:
            save_tree(tree)
            updated += 1
    return updated


def delete_tree(tree_id: str) -> None:
    """删除整棵研究树。"""
    path = _tree_path(tree_id)
    if not path.exists():
        raise FileNotFoundError(f"tree not found: {tree_id}")
    path.unlink()


def rename_tree(tree_id: str, title: str) -> dict[str, Any]:
    """重命名研究树。"""
    tree = load_tree(tree_id)
    tree["title"] = title
    tree["updated_at"] = _now()
    save_tree(tree)
    return tree


def _collect_descendants(tree: dict[str, Any], node_id: str) -> set[str]:
    """收集 node_id 的所有后代节点 id（不含自身）。"""
    by_parent: dict[str, list[dict[str, Any]]] = {}
    for n in tree.get("nodes") or []:
        by_parent.setdefault(n.get("parent_id"), []).append(n)
    result: set[str] = set()
    stack = list(by_parent.get(node_id) or [])
    while stack:
        node = stack.pop()
        nid = node["id"]
        if nid not in result:
            result.add(nid)
            stack.extend(by_parent.get(nid) or [])
    return result


def delete_node(tree_id: str, node_id: str) -> dict[str, Any]:
    """删除节点及其所有后代。根 topic 节点不可删除。"""
    tree = load_tree(tree_id)
    node = _find_node(tree, node_id)
    if not node:
        raise FileNotFoundError(f"node not found: {node_id}")
    if node["kind"] == "topic":
        raise ValueError("cannot delete root topic node")
    descendants = _collect_descendants(tree, node_id)
    remove_ids = {node_id} | descendants
    tree["nodes"] = [n for n in tree["nodes"] if n["id"] not in remove_ids]
    tree["updated_at"] = _now()
    save_tree(tree)
    return node


def tree_to_markmap(tree: dict[str, Any]) -> str:
    """Export tree as Markmap-compatible Markdown."""
    nodes = tree.get("nodes") or []
    by_parent: dict[str | None, list[dict[str, Any]]] = {}
    for n in nodes:
        by_parent.setdefault(n.get("parent_id"), []).append(n)

    def kind_label(kind: str) -> str:
        return {
            "topic": "主题",
            "search": "搜罗",
            "note": "笔记",
            "insight": "要点",
            "ask": "追问",
        }.get(kind, kind)

    lines: list[str] = [f"# {tree.get('title') or '研究'}"]

    def walk(parent_id: str | None, depth: int) -> None:
        for node in by_parent.get(parent_id) or []:
            prefix = "#" * min(6, depth + 2)
            title = node.get("title") or ""
            extra = ""
            if node.get("kind") == "search" and node.get("run_id"):
                extra = f" ({node['run_id']})"
            payload = str(node.get("payload") or "").strip()
            line = f"{prefix} [{kind_label(node.get('kind', ''))}] {title}{extra}"
            lines.append(line)
            if payload and node.get("kind") != "search":
                lines.append(f"{prefix}# {payload[:200]}")
            walk(node.get("id"), depth + 1)

    roots = by_parent.get(None) or []
    if len(roots) == 1:
        walk(roots[0].get("id"), 1)
    else:
        walk(None, 1)
    return "\n".join(lines)
