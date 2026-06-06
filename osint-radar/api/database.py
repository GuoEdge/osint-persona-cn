# SQLite 数据库操作模块

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any, Dict, List, Optional

# 数据库文件路径
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "osint.db")

# 建表 DDL
_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS search_queries (
    query_id TEXT PRIMARY KEY,
    keyword TEXT NOT NULL,
    days INTEGER DEFAULT 7,
    platforms TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS platform_results (
    id TEXT PRIMARY KEY,
    query_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    title TEXT,
    content TEXT,
    url TEXT,
    author TEXT,
    publish_time TIMESTAMP,
    comment_count INTEGER DEFAULT 0,
    raw_data TEXT
);

CREATE TABLE IF NOT EXISTS danmaku_analyses (
    id TEXT PRIMARY KEY,
    query_id TEXT NOT NULL,
    video_url TEXT,
    video_title TEXT,
    total_danmaku INTEGER DEFAULT 0,
    positive INTEGER DEFAULT 0,
    neutral INTEGER DEFAULT 0,
    negative INTEGER DEFAULT 0,
    avg_score REAL DEFAULT 0,
    wordcloud_path TEXT,
    report_path TEXT,
    top_words TEXT
);

CREATE TABLE IF NOT EXISTS video_transcripts (
    id TEXT PRIMARY KEY,
    query_id TEXT NOT NULL,
    video_url TEXT,
    video_title TEXT,
    transcript_path TEXT,
    status TEXT DEFAULT 'pending'
);
"""


def get_connection() -> sqlite3.Connection:
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """初始化数据库，创建所有表"""
    conn = get_connection()
    try:
        conn.executescript(_CREATE_TABLES_SQL)
        conn.commit()
    finally:
        conn.close()


# ========== search_queries 表操作 ==========

def insert_search_query(
    query_id: str,
    keyword: str,
    days: int,
    platforms: str,
    status: str = "pending",
) -> None:
    """插入搜索查询记录"""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO search_queries (query_id, keyword, days, platforms, status) VALUES (?, ?, ?, ?, ?)",
            (query_id, keyword, days, platforms, status),
        )
        conn.commit()
    finally:
        conn.close()


def update_search_status(query_id: str, status: str) -> None:
    """更新搜索状态"""
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE search_queries SET status = ? WHERE query_id = ?",
            (status, query_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_search_query(query_id: str) -> Optional[Dict[str, Any]]:
    """获取搜索查询记录"""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM search_queries WHERE query_id = ?",
            (query_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_search_history(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """获取搜索历史"""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM search_queries ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_search_history_count() -> int:
    """获取搜索历史总数"""
    conn = get_connection()
    try:
        row = conn.execute("SELECT COUNT(*) as cnt FROM search_queries").fetchone()
        return row["cnt"] if row else 0
    finally:
        conn.close()


# ========== platform_results 表操作 ==========

def insert_platform_result(
    result_id: str,
    query_id: str,
    platform: str,
    title: Optional[str] = None,
    content: Optional[str] = None,
    url: Optional[str] = None,
    author: Optional[str] = None,
    publish_time: Optional[str] = None,
    comment_count: int = 0,
    raw_data: Optional[str] = None,
) -> None:
    """插入平台搜索结果"""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO platform_results
               (id, query_id, platform, title, content, url, author, publish_time, comment_count, raw_data)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (result_id, query_id, platform, title, content, url, author, publish_time, comment_count, raw_data),
        )
        conn.commit()
    finally:
        conn.close()


def insert_platform_results_batch(rows: List[tuple]) -> None:
    """批量插入平台搜索结果"""
    if not rows:
        return
    conn = get_connection()
    try:
        conn.executemany(
            """INSERT OR REPLACE INTO platform_results
               (id, query_id, platform, title, content, url, author, publish_time, comment_count, raw_data)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def get_platform_results(query_id: str) -> List[Dict[str, Any]]:
    """获取某次搜索的平台结果"""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM platform_results WHERE query_id = ?",
            (query_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


# ========== danmaku_analyses 表操作 ==========

def insert_danmaku_analysis(
    analysis_id: str,
    query_id: str,
    video_url: Optional[str] = None,
    video_title: Optional[str] = None,
    total_danmaku: int = 0,
    positive: int = 0,
    neutral: int = 0,
    negative: int = 0,
    avg_score: float = 0.0,
    wordcloud_path: Optional[str] = None,
    report_path: Optional[str] = None,
    top_words: Optional[str] = None,
) -> None:
    """插入弹幕分析记录"""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO danmaku_analyses
               (id, query_id, video_url, video_title, total_danmaku, positive, neutral, negative,
                avg_score, wordcloud_path, report_path, top_words)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (analysis_id, query_id, video_url, video_title, total_danmaku, positive, neutral, negative,
             avg_score, wordcloud_path, report_path, top_words),
        )
        conn.commit()
    finally:
        conn.close()


def update_danmaku_analysis(
    analysis_id: str,
    video_title: Optional[str] = None,
    total_danmaku: Optional[int] = None,
    positive: Optional[int] = None,
    neutral: Optional[int] = None,
    negative: Optional[int] = None,
    avg_score: Optional[float] = None,
    wordcloud_path: Optional[str] = None,
    report_path: Optional[str] = None,
    top_words: Optional[str] = None,
) -> None:
    """更新弹幕分析结果"""
    conn = get_connection()
    try:
        fields = []
        values: list[Any] = []
        if video_title is not None:
            fields.append("video_title = ?")
            values.append(video_title)
        if total_danmaku is not None:
            fields.append("total_danmaku = ?")
            values.append(total_danmaku)
        if positive is not None:
            fields.append("positive = ?")
            values.append(positive)
        if neutral is not None:
            fields.append("neutral = ?")
            values.append(neutral)
        if negative is not None:
            fields.append("negative = ?")
            values.append(negative)
        if avg_score is not None:
            fields.append("avg_score = ?")
            values.append(avg_score)
        if wordcloud_path is not None:
            fields.append("wordcloud_path = ?")
            values.append(wordcloud_path)
        if report_path is not None:
            fields.append("report_path = ?")
            values.append(report_path)
        if top_words is not None:
            fields.append("top_words = ?")
            values.append(top_words)
        if not fields:
            return
        values.append(analysis_id)
        conn.execute(
            f"UPDATE danmaku_analyses SET {', '.join(fields)} WHERE id = ?",
            values,
        )
        conn.commit()
    finally:
        conn.close()


def get_danmaku_analyses(query_id: str) -> List[Dict[str, Any]]:
    """获取某次搜索的弹幕分析结果"""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM danmaku_analyses WHERE query_id = ?",
            (query_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_danmaku_analysis_by_id(analysis_id: str) -> Optional[Dict[str, Any]]:
    """根据ID获取弹幕分析结果"""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM danmaku_analyses WHERE id = ?",
            (analysis_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ========== video_transcripts 表操作 ==========

def insert_video_transcript(
    transcript_id: str,
    query_id: str,
    video_url: Optional[str] = None,
    video_title: Optional[str] = None,
    transcript_path: Optional[str] = None,
    status: str = "pending",
) -> None:
    """插入视频转文字记录"""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO video_transcripts
               (id, query_id, video_url, video_title, transcript_path, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (transcript_id, query_id, video_url, video_title, transcript_path, status),
        )
        conn.commit()
    finally:
        conn.close()


def update_video_transcript(
    transcript_id: str,
    video_title: Optional[str] = None,
    transcript_path: Optional[str] = None,
    status: Optional[str] = None,
) -> None:
    """更新视频转文字记录"""
    conn = get_connection()
    try:
        fields = []
        values: list[Any] = []
        if video_title is not None:
            fields.append("video_title = ?")
            values.append(video_title)
        if transcript_path is not None:
            fields.append("transcript_path = ?")
            values.append(transcript_path)
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if not fields:
            return
        values.append(transcript_id)
        conn.execute(
            f"UPDATE video_transcripts SET {', '.join(fields)} WHERE id = ?",
            values,
        )
        conn.commit()
    finally:
        conn.close()


def get_video_transcripts(query_id: str) -> List[Dict[str, Any]]:
    """获取某次搜索的视频转文字结果"""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM video_transcripts WHERE query_id = ?",
            (query_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_video_transcript_by_id(transcript_id: str) -> Optional[Dict[str, Any]]:
    """根据ID获取视频转文字记录"""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM video_transcripts WHERE id = ?",
            (transcript_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
