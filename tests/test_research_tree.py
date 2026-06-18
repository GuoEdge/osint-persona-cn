"""Research tree tests."""

from __future__ import annotations

import pytest

from osint_toolkit.research.tree import (
    add_node,
    attach_search_node,
    create_tree,
    load_tree,
    tree_to_markmap,
    update_search_node_status,
)


def test_create_tree_and_add_search_node(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.research.tree.get_data_dir", lambda: tmp_path)
    tree = create_tree("MCP 协议", query="MCP")
    root_id = tree["nodes"][0]["id"]
    node = attach_search_node(
        tree["id"],
        parent_node_id=root_id,
        run_id="run-abc",
        query="MCP",
    )
    assert node["kind"] == "search"
    assert node["run_id"] == "run-abc"
    loaded = load_tree(tree["id"])
    assert len(loaded["nodes"]) == 2


def test_update_search_node_status(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.research.tree.get_data_dir", lambda: tmp_path)
    tree = create_tree("测试")
    root_id = tree["nodes"][0]["id"]
    attach_search_node(tree["id"], parent_node_id=root_id, run_id="r1", query="q")
    update_search_node_status(tree["id"], "r1", status="done")
    loaded = load_tree(tree["id"])
    search_nodes = [n for n in loaded["nodes"] if n["kind"] == "search"]
    assert search_nodes[0]["meta"]["status"] == "done"


def test_tree_to_markmap(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.research.tree.get_data_dir", lambda: tmp_path)
    tree = create_tree("根主题")
    root_id = tree["nodes"][0]["id"]
    add_node(tree["id"], parent_id=root_id, kind="note", title="笔记", payload="内容")
    md = tree_to_markmap(load_tree(tree["id"]))
    assert "根主题" in md
    assert "笔记" in md
