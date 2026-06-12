"""Web API 测试."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.web.app import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


def test_page_workspace(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "搜罗" in r.text
    assert "nav_groups" not in r.text  # rendered, not variable name
    assert "个人情报" in r.text


def test_page_routes(client):
    for path in ["/save", "/knowledge", "/digest", "/persona", "/ingest", "/behavior", "/runs", "/ai", "/settings"]:
        r = client.get(path)
        assert r.status_code == 200, path


def test_auth_status(client):
    r = client.get("/api/auth/status")
    assert r.status_code == 200
    data = r.json()
    assert "items" in data


def test_setup_status(client):
    r = client.get("/api/setup/status")
    assert r.status_code == 200
    data = r.json()
    assert "steps" in data
    assert "ready" in data


def test_ingest_capabilities(client):
    r = client.get("/api/ingest/capabilities")
    assert r.status_code == 200
    assert "items" in r.json()


def test_auth_paths(client):
    r = client.get("/api/auth/paths")
    assert r.status_code == 200
    assert "data_dir" in r.json()


def test_knowledge_items(client, tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: tmp_path / "knowledge.db")
    r = client.get("/api/knowledge/items?limit=5")
    assert r.status_code == 200
    assert "items" in r.json()


def test_runs_list(client, tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.services.runs.get_data_dir", lambda: tmp_path)
    (tmp_path / "runs").mkdir(parents=True, exist_ok=True)
    r = client.get("/api/runs")
    assert r.status_code == 200
    assert r.json()["runs"] == []


def test_search_async(client, monkeypatch):
    async def fake_search(**kwargs):
        return {
            "run_id": kwargs.get("run_id", "test-run"),
            "items": [
                IntelItem(source="web", type="test", url="https://x.com", title="Test", content="c"),
            ],
            "report": "",
            "report_path": None,
            "simulations": [],
            "run_dir": "/tmp",
        }

    async def fake_execute(run_id, **kwargs):
        from osint_toolkit.web import tasks

        tasks._jobs[run_id] = {"status": "done", "result": await fake_search(**kwargs, run_id=run_id), "error": None}

    def fake_start(**kwargs):
        from osint_toolkit.web import tasks

        run_id = "20260101-120000-test1234"
        tasks._jobs[run_id] = {"status": "running", "result": None, "error": None}
        import asyncio

        asyncio.get_event_loop().create_task(fake_execute(run_id, **kwargs))
        return run_id

    monkeypatch.setattr("osint_toolkit.web.routes.api.start_search_job", fake_start)

    r = client.post("/api/search", json={"query": "test", "sources": ["web"], "no_ai": True})
    assert r.status_code == 200
    assert r.json()["status"] == "running"
    assert "run_id" in r.json()


def test_ai_directives(client, tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.ai.steering.directives_path", lambda: tmp_path / "ai_directives.yaml")
    r = client.get("/api/ai/directives")
    assert r.status_code == 200
    body = {"data": {"hard_constraints": ["test"], "soft_preferences": {}}}
    r2 = client.put("/api/ai/directives", json=body)
    assert r2.status_code == 200


def test_ai_prompts(client, tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.ai.prompt_loader.get_data_dir", lambda: tmp_path)
    r = client.get("/api/ai/prompts")
    assert r.status_code == 200
    assert "prompts" in r.json()


def test_feedback(client, tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.feedback.store.get_data_dir", lambda: tmp_path)
    r = client.post(
        "/api/feedback",
        json={"target_id": "item-1", "rating": "useful", "run_id": "run-1"},
    )
    assert r.status_code == 200
    assert "entry" in r.json()

    r2 = client.get("/api/feedback/recent?target_ids=item-1")
    assert r2.status_code == 200
    assert r2.json()["feedback"]["item:item-1"] == "useful"


def test_aicu_status(client, monkeypatch):
    monkeypatch.setattr(
        "osint_toolkit.utils.config.load_config",
        lambda: {"ingest": {"aicu_enabled": True}},
    )
    r = client.get("/api/ingest/aicu-status")
    assert r.status_code == 200
    assert r.json()["enabled"] is True


def test_run_detail_skips_list_artifacts(client, tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.services.runs.get_data_dir", lambda: tmp_path)
    run_dir = tmp_path / "runs" / "20260101-120000-test1234"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        '{"run_id":"20260101-120000-test1234","command":"search","query":"x","steps":[]}',
        encoding="utf-8",
    )
    (run_dir / "01_collect_all.json").write_text('{"step":"collect_all","status":"ok"}', encoding="utf-8")
    (run_dir / "items_raw.json").write_text("[{}]", encoding="utf-8")
    r = client.get("/api/runs/20260101-120000-test1234")
    assert r.status_code == 200
    assert len(r.json()["steps"]) == 1
