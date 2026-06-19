"""SQLite connection pool tests."""

from __future__ import annotations

from osint_toolkit.storage import sqlite as sqlite_mod


def test_connect_returns_pooled_wrapper(tmp_path, monkeypatch):
    monkeypatch.setattr(sqlite_mod, "get_data_dir", lambda: tmp_path)
    conn = sqlite_mod.connect()
    assert hasattr(conn, "execute")
    conn.execute("SELECT 1")
    conn.close()
    conn2 = sqlite_mod.connect()
    conn2.execute("SELECT 1")
    conn2.close()
