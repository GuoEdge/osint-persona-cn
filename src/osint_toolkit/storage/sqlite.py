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


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
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
            title, content, summary, tokenize='unicode61'
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
        """
    )
    conn.commit()
