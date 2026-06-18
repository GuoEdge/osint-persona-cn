"""API tests for search session endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from osint_toolkit.web.app import create_app


def test_search_active_endpoint():
    client = TestClient(create_app())
    r = client.get("/api/search/active")
    assert r.status_code == 200
    assert "searches" in r.json()


def test_jobs_active_endpoint():
    client = TestClient(create_app())
    r = client.get("/api/jobs/active")
    assert r.status_code == 200
    assert "jobs" in r.json()


def test_api_search_strips_session_keys_before_run_search():
    captured: dict = {}
    done = False

    async def fake_run_search(**kwargs):
        captured.update(kwargs)
        nonlocal done
        done = True
        return {
            "run_id": kwargs.get("run_id") or "test-run",
            "items": [],
            "report": "",
            "report_path": None,
            "simulations": [],
        }

    with patch("osint_toolkit.services.search.run_search", new=AsyncMock(side_effect=fake_run_search)):
        client = TestClient(create_app())
        r = client.post(
            "/api/search",
            json={
                "query": "测试",
                "sources": ["web"],
                "create_tree": True,
            },
        )
        assert r.status_code == 200
        run_id = r.json().get("run_id")
        for _ in range(50):
            if done:
                break
            client.get(f"/api/search/{run_id}")
    assert "tree_id" not in captured
    assert "parent_node_id" not in captured
    assert "create_tree" not in captured
    assert captured.get("query") == "测试"
