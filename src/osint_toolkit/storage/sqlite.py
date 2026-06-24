"""SQLite 存储 / SQLite storage."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from osint_toolkit.auth.paths import get_data_dir

_POOL_LOCK = threading.Lock()
_POOL: list[sqlite3.Connection] = []
_MAX_POOL_SIZE = 5
_POOL_DB_PATH: Path | None = None
_SCHEMA_READY: set[str] = set()


def _reset_pool_if_path_changed(path: Path) -> None:
    global _POOL_DB_PATH
    with _POOL_LOCK:
        if _POOL_DB_PATH == path:
            return
        for conn in _POOL:
            try:
                conn.close()
            except sqlite3.Error:
                pass
        _POOL.clear()
        _SCHEMA_READY.clear()
        _POOL_DB_PATH = path


def get_db_path() -> Path:
    return get_data_dir() / "knowledge.db"


class _PooledConnection:
    """包装连接：close() 归还连接池而非真正关闭。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def __getattr__(self, name: str):
        return getattr(self._conn, name)

    def close(self) -> None:
        _release_connection(self._conn)

    def __enter__(self) -> _PooledConnection:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _create_connection() -> sqlite3.Connection:
    path = get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    if str(path) not in _SCHEMA_READY:
        init_schema(conn)
        with _POOL_LOCK:
            _SCHEMA_READY.add(str(path))
    return conn


def _release_connection(conn: sqlite3.Connection) -> None:
    try:
        conn.rollback()
    except sqlite3.Error:
        try:
            conn.close()
        except sqlite3.Error:
            pass
        return
    with _POOL_LOCK:
        if len(_POOL) < _MAX_POOL_SIZE:
            _POOL.append(conn)
            return
    try:
        conn.close()
    except sqlite3.Error:
        pass


def connect() -> _PooledConnection:
    path = get_db_path()
    _reset_pool_if_path_changed(path)
    with _POOL_LOCK:
        while _POOL:
            conn = _POOL.pop()
            try:
                conn.execute("SELECT 1")
                return _PooledConnection(conn)
            except sqlite3.Error:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass
    return _PooledConnection(_create_connection())


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
        CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
        CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at);
        CREATE INDEX IF NOT EXISTS idx_intel_source ON intel_items(source);
        CREATE INDEX IF NOT EXISTS idx_intel_url ON intel_items(url);
        CREATE INDEX IF NOT EXISTS idx_intel_created ON intel_items(created_at);
        CREATE INDEX IF NOT EXISTS idx_intel_source_created ON intel_items(source, created_at);
        CREATE INDEX IF NOT EXISTS idx_endorsements_endorsed ON endorsements(endorsed_at);
        """
    )
    conn.commit()
    _migrate_fts(conn)
