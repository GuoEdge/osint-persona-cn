"""Setup sync tracking tests."""

from pathlib import Path

from osint_toolkit.services.setup import get_last_full_sync_at, get_setup_status, record_full_sync


def test_record_full_sync(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.services.setup.get_data_dir", lambda: tmp_path)
    assert get_last_full_sync_at() is None
    record_full_sync()
    assert get_last_full_sync_at() is not None


def test_setup_status_has_sync_step(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.services.setup.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "osint_toolkit.services.setup.auth.get_auth_status",
        lambda _t: [{"key": "bilibili", "ok": True}],
    )
    monkeypatch.setattr("osint_toolkit.services.setup.connect", lambda: _FakeConn())
    monkeypatch.setattr("osint_toolkit.services.setup.load_mental_model", lambda: {"version": 0})
    monkeypatch.setattr("osint_toolkit.services.setup.load_persona_brief", lambda: "")
    monkeypatch.setattr("osint_toolkit.services.setup.is_persona_stale", lambda: False)
    monkeypatch.setattr("osint_toolkit.services.setup._extension_connected", lambda: False)
    monkeypatch.setattr("osint_toolkit.services.setup._has_search_run", lambda: False)
    monkeypatch.setattr(
        "osint_toolkit.services.dependencies.get_dependencies_status",
        lambda: {"playwright_installed": False, "items": [], "blockers": []},
    )
    monkeypatch.setattr("osint_toolkit.services.dependencies.playwright_available", lambda: False)

    status = get_setup_status()
    ids = [s["id"] for s in status["steps"]]
    assert ids == ["deepseek", "zhihu_openapi", "playwright", "cookies", "sync", "extension", "search", "persona"]
    sync_step = next(s for s in status["steps"] if s["id"] == "sync")
    assert sync_step["done"] is False

    record_full_sync()
    status2 = get_setup_status()
    sync_step2 = next(s for s in status2["steps"] if s["id"] == "sync")
    assert sync_step2["done"] is True


class _FakeConn:
    def execute(self, sql, *args):
        return _FakeRow()

    def close(self):
        pass


class _FakeRow:
    def fetchone(self):
        return {"c": 0}

    def __iter__(self):
        return iter([])
