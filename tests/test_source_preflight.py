"""Source auth preflight tests."""

from __future__ import annotations

import pytest

from osint_toolkit.services.source_preflight import apply_auth_gates, check_source_auth


def test_bilibili_requires_cookie(monkeypatch):
    monkeypatch.setattr(
        "osint_toolkit.services.source_preflight.validate_domain_cookie",
        lambda domain: {"ok": False, "reason": "未找到同步文件"},
    )
    check = check_source_auth("bilibili")
    assert check["ok"] is False
    assert check["action"] == "sync_cookies"


def test_music_uses_serp_without_cookie(monkeypatch):
    monkeypatch.setattr(
        "osint_toolkit.services.source_preflight.validate_domain_cookie",
        lambda domain: {"ok": False, "reason": "未找到同步文件"},
    )
    check = check_source_auth("netease_music")
    assert check["ok"] is True
    assert check["using_serp_fallback"] is True


def test_apply_auth_gates_skips_bilibili_keeps_web(monkeypatch):
    monkeypatch.setattr(
        "osint_toolkit.services.source_preflight.validate_domain_cookie",
        lambda domain: {"ok": False, "reason": "未同步"},
    )

    def fake_api(key):
        raise RuntimeError("no key")

    monkeypatch.setattr("osint_toolkit.services.source_preflight.resolve_secret", fake_api)
    result = apply_auth_gates(["bilibili", "web", "netease_music"])
    assert "bilibili" in result["skipped_sources"]
    assert "web" in result["allowed_sources"]
    assert "netease_music" in result["allowed_sources"]


def test_apply_auth_gates_bilibili_serp_when_accepted(monkeypatch):
    monkeypatch.setattr(
        "osint_toolkit.services.source_preflight.validate_domain_cookie",
        lambda domain: {"ok": False, "reason": "未同步"},
    )
    result = apply_auth_gates(["bilibili"], serp_fallback_accepted=["bilibili"])
    assert "bilibili" in result["allowed_sources"]
    assert "bilibili" not in result["skipped_sources"]


def test_check_source_auth_ui_status(monkeypatch):
    monkeypatch.setattr(
        "osint_toolkit.services.source_preflight.validate_domain_cookie",
        lambda domain: {"ok": True, "reason": "ok"},
    )
    check = check_source_auth("web")
    assert check["ui_status"] == "none"


def test_zhihu_ok_with_openapi(monkeypatch):
    monkeypatch.setattr(
        "osint_toolkit.services.source_preflight.validate_domain_cookie",
        lambda domain: {"ok": False, "reason": "未同步"},
    )
    monkeypatch.setattr("osint_toolkit.services.source_preflight.resolve_secret", lambda key: "secret")
    check = check_source_auth("zhihu")
    assert check["ok"] is True
