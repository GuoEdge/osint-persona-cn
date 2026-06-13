"""Config merge and operations tests."""

from osint_toolkit.services.ops import get_operations_runbook
from osint_toolkit.utils.config import get_aicu_enabled


def test_aicu_enabled_merges_sync_and_ingest(monkeypatch):
    monkeypatch.setattr(
        "osint_toolkit.utils.config.load_config",
        lambda: {
            "sync": {"aicu_enabled": False},
            "ingest": {"aicu_enabled": True},
        },
    )
    assert get_aicu_enabled() is True

    monkeypatch.setattr(
        "osint_toolkit.utils.config.load_config",
        lambda: {
            "sync": {"aicu_enabled": True},
            "ingest": {"aicu_enabled": False},
        },
    )
    assert get_aicu_enabled() is True


def test_operations_runbook_has_recommended_steps():
    book = get_operations_runbook()
    assert len(book["recommended"]) >= 4
    assert book["sync_modes"]["full"]["label"] == "完整同步"
