"""Delivery readiness API smoke tests (batch save, watches, research)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.web.app import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


def test_api_save_run_items(client, tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("osint_toolkit.services.save.get_data_dir", lambda: tmp_path)
    run_id = "20260101-120000-0a1b2c3d"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    item = IntelItem(source="web", type="t", url="https://example.com/a", title="A", content="c")
    item.signals.relevance = 0.9
    (run_dir / "03_items_dedup.json").write_text(
        json.dumps([item.to_dict()]),
        encoding="utf-8",
    )
    saved: list[str] = []

    def fake_save(it):
        saved.append(it.id)

    monkeypatch.setattr("osint_toolkit.services.save.save_item", fake_save)
    r = client.post(f"/api/search/{run_id}/save-items", json={"min_relevance": 0.5})
    assert r.status_code == 200
    body = r.json()
    assert body.get("saved_count") == 1
    assert saved == [item.id]


def test_api_watches_list(client, monkeypatch):
    monkeypatch.setattr(
        "osint_toolkit.services.watch.load_watches",
        lambda: [{"id": "w1", "query": "test", "schedule": "6h", "enabled": True}],
    )
    r = client.get("/api/watches")
    assert r.status_code == 200
    watches = r.json().get("watches") or []
    assert len(watches) == 1
    assert watches[0]["id"] == "w1"


def test_api_research_trees_crud(client, tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.research.tree.get_data_dir", lambda: tmp_path)
    created = client.post("/api/research/trees", json={"title": "交付测试", "query": "话题"})
    assert created.status_code == 200
    tree = created.json()["tree"]
    tree_id = tree["id"]
    root_id = tree["nodes"][0]["id"]

    listed = client.get("/api/research/trees")
    assert listed.status_code == 200
    assert any(t["id"] == tree_id for t in listed.json().get("trees") or [])

    node = client.post(
        f"/api/research/trees/{tree_id}/nodes",
        json={"parent_id": root_id, "kind": "note", "title": "子节点"},
    )
    assert node.status_code == 200
    assert node.json()["node"]["parent_id"] == root_id

    got = client.get(f"/api/research/trees/{tree_id}")
    assert got.status_code == 200
    assert len(got.json()["tree"]["nodes"]) >= 2


def test_comment_mine_sources_documented():
    from osint_toolkit.collectors.comment_mine_registry import COMMENT_MINE_SOURCES

    assert COMMENT_MINE_SOURCES == {"bilibili", "zhihu", "v2ex"}


def test_subtitle_pick_ai_vs_cc():
    from osint_toolkit.processors.subtitle import pick_subtitle_track

    tracks = [
        {"lan": "zh-CN", "lan_doc": "中文", "subtitle_url": "https://example.com/cc"},
        {"lan": "zh-CN", "lan_doc": "中文（自动生成）", "subtitle_url": "https://example.com/ai"},
    ]
    picked = pick_subtitle_track(tracks)
    assert picked is not None
    assert "自动" in picked.get("lan_doc", "")
