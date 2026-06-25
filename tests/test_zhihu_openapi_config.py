"""Regression tests for openapi.enabled config default."""

from __future__ import annotations

from unittest.mock import patch


def test_openapi_enabled_defaults_true_when_only_secret_set(tmp_path, monkeypatch):
    """User config with only access_secret should have openapi enabled by default."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "zhihu:\n  openapi:\n    access_secret: abc123\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("osint_toolkit.utils.config._CONFIG_CACHE", None)
    monkeypatch.setattr("osint_toolkit.utils.config._CONFIG_KEY", None)
    from osint_toolkit.utils.config import load_config
    from osint_toolkit.ingest import zhihu_openapi

    monkeypatch.setattr("osint_toolkit.utils.config.get_config_paths", lambda: [config_file])
    with patch.dict("os.environ", {}, clear=True):
        cfg = load_config()
    openapi_cfg = cfg.get("zhihu", {}).get("openapi", {})
    assert openapi_cfg.get("access_secret") == "abc123"
    assert openapi_cfg.get("enabled", True) is True
    assert zhihu_openapi.openapi_configured() is True


def test_openapi_disabled_when_user_explicitly_sets_false(tmp_path, monkeypatch):
    """User config with enabled: false should disable openapi."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "zhihu:\n  openapi:\n    enabled: false\n    access_secret: abc123\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("osint_toolkit.utils.config._CONFIG_CACHE", None)
    monkeypatch.setattr("osint_toolkit.utils.config._CONFIG_KEY", None)
    from osint_toolkit.ingest import zhihu_openapi

    monkeypatch.setattr("osint_toolkit.utils.config.get_config_paths", lambda: [config_file])
    assert zhihu_openapi.openapi_configured() is False
