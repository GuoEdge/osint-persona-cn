"""SQLite 存储 / SQLite storage."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from osint_toolkit.auth.paths import get_data_dir


def get_db_path() -> Path:
    return get_data_dir() / "knowledge.db"


def connect() -> sqlite3.Connection:
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_schema(conn)
    return conn


def _migrate_fts(conn: sqlite3.Connection) -> None:
    row = conn.execute(
        "SELECT value FROM meta WHERE key = 'fts_schema_version'"
    ).fetchone()
    version = int(row["value"]) if row else 0
    if version >= 2:
        return
    conn.execute("DROP TABLE IF EXISTS intel_fts")
    conn.execute(
        """
        CREATE VIRTUAL TABLE intel_fts USING fts5(
            item_id UNINDEXED, title, content, summary, tokenize='unicode61'
        )
        """
    )
    rows = conn.execute("SELECT id, title, content, data_json FROM intel_items").fetchall()
    for row in rows:
        summary = ""
        try:
            import json

            data = json.loads(row["data_json"] or "{}")
            summary = str(data.get("summary") or "")
        except (json.JSONDecodeError, TypeError):
            pass
        conn.execute(
            "INSERT INTO intel_fts (item_id, title, content, summary) VALUES (?, ?, ?, ?)",
            (row["id"], row["title"] or "", row["content"] or "", summary),
        )
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('fts_schema_version', '2')"
    )
    conn.commit()


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS intel_items (
            id TEXT PRIMARY KEY,
            source TEXT,
            type TEXT,
            url TEXT,
            title TEXT,
            content TEXT,
            data_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS intel_fts USING fts5(
            item_id UNINDEXED, title, content, summary, tokenize='unicode61'
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT,
            data_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS endorsements (
            id TEXT PRIMARY KEY,
            platform TEXT,
            target_type TEXT,
            url TEXT,
            content TEXT,
            data_json TEXT,
            endorsed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS event_dedup (
            dedup_key TEXT PRIMARY KEY,
            event_type TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.commit()
    _migrate_fts(conn)
