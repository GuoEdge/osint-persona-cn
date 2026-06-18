"""Research tree PATCH API tests."""

from __future__ import annotations

from osint_toolkit.research.tree import add_node, create_tree, load_tree, patch_node


def test_patch_node_title_and_payload(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.research.tree.get_data_dir", lambda: tmp_path)
    tree = create_tree("测试主题")
    root_id = tree["nodes"][0]["id"]
    note = add_node(tree["id"], parent_id=root_id, kind="note", title="旧标题", payload="旧内容")
    updated = patch_node(tree["id"], note["id"], title="新标题", payload="新内容\n第二行")
    assert updated["title"] == "新标题"
    assert updated["payload"] == "新内容\n第二行"
    loaded = load_tree(tree["id"])
    node = next(n for n in loaded["nodes"] if n["id"] == note["id"])
    assert node["payload"] == "新内容\n第二行"
