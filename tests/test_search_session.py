"""Search session persistence tests."""

from __future__ import annotations

import json

import pytest

from osint_toolkit.auth.paths import get_data_dir
from osint_toolkit.pipeline.progress import get_progress, init_progress, update_progress
from osint_toolkit.services.search_fork import build_fork_search_params
from osint_toolkit.research.tree import attach_search_node, create_tree, find_search_node_id_for_run
from osint_toolkit.services.run_session import read_manifest, read_progress_disk, set_run_status
from osint_toolkit.services.search_params import strip_session_keys
from osint_toolkit.web.tasks import _search_run_kwargs


def test_search_run_kwargs_strips_session_metadata():
    raw = {
        "query": "MCP",
        "sources": ["zhihu"],
        "tree_id": "tree-1",
        "parent_node_id": "node-1",
        "fork_from_run_id": "run-old",
        "create_tree": True,
    }
    filtered = _search_run_kwargs(raw)
    assert filtered == {"query": "MCP", "sources": ["zhihu"]}
    assert strip_session_keys(raw) == filtered


def test_fork_does_not_inherit_session_keys_from_parent_request(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.services.search_fork.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("osint_toolkit.services.run_session.get_data_dir", lambda: tmp_path)
    run_id = "fork-src"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "request.json").write_text(
        json.dumps(
            {
                "query": "MCP",
                "sources": ["zhihu"],
                "tree_id": "old-tree",
                "parent_node_id": "old-node",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    merged = build_fork_search_params(
        run_id,
        {"query": "MCP 深化", "tree_id": "new-tree", "parent_node_id": "new-node"},
    )
    assert merged["tree_id"] == "new-tree"
    assert merged["parent_node_id"] == "new-node"
    assert "old-tree" not in str(merged.get("tree_id"))
    assert merged.get("sources") == ["zhihu"]


def test_find_search_node_id_for_run(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.research.tree.get_data_dir", lambda: tmp_path)
    tree = create_tree("主题")
    root_id = tree["nodes"][0]["id"]
    attach_search_node(tree["id"], parent_node_id=root_id, run_id="run-a", query="A")
    assert find_search_node_id_for_run(tree["id"], "run-a") is not None
    assert find_search_node_id_for_run(tree["id"], "missing") is None


def test_run_status_and_request_on_disk(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.services.run_session.get_data_dir", lambda: tmp_path)
    run_id = "test-run-001"
    req = {"query": "MCP", "sources": ["zhihu"]}
    set_run_status(run_id, "running", request=req)
    manifest = read_manifest(run_id)
    assert manifest is not None
    assert manifest["status"] == "running"
    assert manifest["request"]["query"] == "MCP"
    set_run_status(run_id, "done")
    manifest = read_manifest(run_id)
    assert manifest["status"] == "done"
    assert manifest.get("finished_at")


def test_progress_disk_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.pipeline.progress.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("osint_toolkit.services.run_session.get_data_dir", lambda: tmp_path)
    run_id = "prog-run"
    init_progress(run_id)
    update_progress(run_id, "collect_all", detail="采集中", collect_done=2, collect_total=5, force_disk=True)
    disk = read_progress_disk(run_id)
    assert disk is not None
    assert disk["phase"] == "collect_all"
    assert disk["collect_done"] == 2
    assert get_progress(run_id) is not None
