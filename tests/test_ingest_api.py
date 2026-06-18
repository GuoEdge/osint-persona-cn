"""Ingest status API smoke tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from osint_toolkit.web.app import create_app


def test_ingest_preflight_shape():
    client = TestClient(create_app())
    r = client.get("/api/ingest/preflight")
    assert r.status_code == 200
    data = r.json()
    assert "ready" in data
    assert "login" in data
    assert "hints" in data


def test_ingest_health_shape():
    client = TestClient(create_app())
    r = client.get("/api/ingest/health")
    assert r.status_code == 200
    data = r.json()
    assert "ok" in data
    assert "events" in data


def test_ingest_capabilities_shape():
    client = TestClient(create_app())
    r = client.get("/api/ingest/capabilities")
    assert r.status_code == 200
    assert "items" in r.json()


def test_auth_status_shape():
    client = TestClient(create_app())
    r = client.get("/api/auth/status")
    assert r.status_code == 200
    items = r.json().get("items") or []
    assert isinstance(items, list)
    if items:
        assert "name" in items[0]
        assert "ok" in items[0]
