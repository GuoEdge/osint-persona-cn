"""Unified sync config tests."""

from osint_toolkit.utils.config import get_browser_sync_config, load_sync_config


def test_load_sync_config_merges_legacy_ingest():
    sync = load_sync_config()
    assert "prefer_server_api" in sync
    assert sync.get("browser_sync_mode") == "auto"
    assert sync.get("max_pages_per_run") == 6


def test_get_browser_sync_config_from_sync():
    bs = get_browser_sync_config()
    assert bs["browser_sync_max_pages"] == 6
    assert bs["browser_sync_scroll_rounds"] == 4
