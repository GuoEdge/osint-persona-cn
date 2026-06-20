"""Tests for tunable config service and API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from osint_toolkit.services import tunable_config
from osint_toolkit.web.app import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


def test_list_tunable_groups():
    data = tunable_config.list_tunable_groups()
    ids = {g["id"] for g in data["groups"]}
    assert "search_concurrency" in ids
    assert "search_fast" in ids
    assert "zhihu_openapi" in ids
    assert "foreign_expand" in ids
    openapi_group = next(g for g in data["groups"] if g["id"] == "zhihu_openapi")
    keys = {f["key"] for f in openapi_group["fields"]}
    assert "zhihu.openapi.min_request_interval_sec" in keys
    foreign_group = next(g for g in data["groups"] if g["id"] == "foreign_expand")
    foreign_keys = {f["key"] for f in foreign_group["fields"]}
    assert "search.foreign_expand.enabled" in foreign_keys
    assert "http.proxy" in foreign_keys


def test_patch_tunable_values(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.yaml"
    written: dict = {}

    def fake_save(patch):
        written.update(patch)
        return str(cfg_path)

    monkeypatch.setattr("osint_toolkit.services.tunable_config.save_user_config_patch", fake_save)

    result = tunable_config.patch_tunable_values(
        {
            "search.max_concurrent_searches": 3,
            "zhihu.openapi.min_request_interval_sec": 1.5,
            "ai.auto_persona_rebuild": "prompt",
        }
    )
    assert result["applied"]["search.max_concurrent_searches"] == 3
    assert written["search"]["max_concurrent_searches"] == 3
    assert written["zhihu"]["openapi"]["min_request_interval_sec"] == 1.5
    assert written["ai"]["auto_persona_rebuild"] == "prompt"


def test_patch_foreign_expand_enabled(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.yaml"
    written: dict = {}

    def fake_save(patch):
        written.update(patch)
        return str(cfg_path)

    monkeypatch.setattr("osint_toolkit.services.tunable_config.save_user_config_patch", fake_save)

    result = tunable_config.patch_tunable_values({"search.foreign_expand.enabled": "on"})
    assert result["applied"]["search.foreign_expand.enabled"] == "on"
    assert written["search"]["foreign_expand"]["enabled"] == "on"


def test_patch_empty_proxy_to_null(tmp_path, monkeypatch):
    written: dict = {}

    monkeypatch.setattr(
        "osint_toolkit.services.tunable_config.save_user_config_patch",
        lambda patch: (written.update(patch), str(tmp_path / "config.yaml"))[1],
    )

    result = tunable_config.patch_tunable_values({"http.proxy": ""})
    assert result["applied"]["http.proxy"] is None
    assert written["http"]["proxy"] is None


def test_patch_proxy_value(tmp_path, monkeypatch):
    written: dict = {}

    monkeypatch.setattr(
        "osint_toolkit.services.tunable_config.save_user_config_patch",
        lambda patch: (written.update(patch), str(tmp_path / "config.yaml"))[1],
    )

    result = tunable_config.patch_tunable_values({"http.proxy": "http://127.0.0.1:7890"})
    assert result["applied"]["http.proxy"] == "http://127.0.0.1:7890"
    assert written["http"]["proxy"] == "http://127.0.0.1:7890"


def test_patch_rejects_unknown_key():
    with pytest.raises(ValueError, match="未知参数"):
        tunable_config.patch_tunable_values({"not.a.real.key": 1})


def test_patch_rejects_out_of_range():
    with pytest.raises(ValueError, match="不能大于"):
        tunable_config.patch_tunable_values({"search.max_concurrent_searches": 99})


def test_config_tunables_api(client):
    r = client.get("/api/config/tunables")
    assert r.status_code == 200
    assert "groups" in r.json()


def test_config_tunables_patch_api(client, tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.yaml"
    monkeypatch.setattr("osint_toolkit.services.tunable_config.save_user_config_patch", lambda patch: str(cfg_path))
    drained = {"called": False}
    monkeypatch.setattr(
        "osint_toolkit.web.routes.api.drain_search_queue",
        lambda: drained.update(called=True),
    )

    r = client.patch(
        "/api/config/tunables",
        json={"values": {"search.max_concurrent_searches": 2}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["applied"]["search.max_concurrent_searches"] == 2
    assert "groups" in body
    assert drained["called"] is True
