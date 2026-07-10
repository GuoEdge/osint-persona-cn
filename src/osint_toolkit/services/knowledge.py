"""知识库服务 / Knowledge base service."""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import UTC, datetime
from typing import Any

from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.persona.behavior_signals import score_event
from osint_toolkit.services import knowledge_graph, knowledge_search
from osint_toolkit.storage.knowledge import delete_item as _delete_item
from osint_toolkit.storage.knowledge import delete_items as _delete_items
from osint_toolkit.storage.knowledge import recall as _recall
from osint_toolkit.storage.knowledge_index import extract_entities_from_payload, extract_tags_from_payload
from osint_toolkit.storage.sqlite import connect, get_db_path


def _temporal_decay(created_at_str: str | None, half_life_days: float = 30.0) -> float:
    if not created_at_str:
        return 0.5
    try:
        created = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        age_days = (datetime.now(UTC) - created).total_seconds() / 86400
        return math.pow(0.5, age_days / half_life_days)
    except (ValueError, TypeError):
        return 0.5


def recall(query: str, limit: int = 20) -> list[IntelItem]:
    hits = knowledge_search.search(query, limit=limit, mode="hybrid", explain=False, include_related=True)
    items = [hit["item"] for hit in hits]
    if items:
        return items
    items = _recall(query, limit=limit)
    q = query.strip()
    if not q:
        return items
    remaining = limit - len(items)
    if remaining <= 0:
        return items
    seen = {i.url for i in items if i.url}
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT event_type, data_json FROM events "
            "WHERE data_json LIKE ? ORDER BY id DESC LIMIT ?",
            (f"%{q}%", remaining * 5),
        ).fetchall()
    finally:
        conn.close()
    for row in rows:
        data = json.loads(row["data_json"])
        if score_event(str(row["event_type"]), data) < 12:
            continue
        url = str(data.get("url") or "")
        title = str(data.get("title") or url or row["event_type"])
        if url and url in seen:
            continue
        if url:
            seen.add(url)
        items.append(
            IntelItem(
                source=str(data.get("source") or "behavior"),
                type="behavior",
                url=url,
                title=title,
                content=f"行为信号: {row['event_type']}",
                personal={"from": "events", "event_type": row["event_type"]},
            )
        )
        if len(items) >= limit:
            break
    for item in items:
        decay = _temporal_decay(item.published_at or item.personal.get("saved_at"))
        item.signals.relevance = (item.signals.relevance or 0.5) * decay
    items.sort(key=lambda i: i.signals.relevance or 0, reverse=True)
    return items


def search(
    query: str,
    *,
    mode: str = "hybrid",
    source: str | None = None,
    topic: str | None = None,
    tag: str | None = None,
    entity: str | None = None,
    run_id: str | None = None,
    capture_reason: str | None = None,
    conflict_status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 20,
    explain: bool = False,
    include_related: bool = True,
) -> list[dict[str, Any]]:
    return knowledge_search.search(
        query,
        mode=mode,
        source=source,
        topic=topic,
        tag=tag,
        entity=entity,
        run_id=run_id,
        capture_reason=capture_reason,
        conflict_status=conflict_status,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        explain=explain,
        include_related=include_related,
    )


def search_suggestions(query: str, *, limit: int = 8) -> dict[str, Any]:
    return knowledge_search.suggest(query, limit=limit)


def health() -> dict[str, Any]:
    """Return a readable diagnosis for the local knowledge runtime."""
    db_path = get_db_path()
    required_tables = {
        "intel_items": "知识条目主表",
        "intel_fts": "全文检索索引",
        "knowledge_concepts": "概念表",
        "knowledge_item_concepts": "条目-概念关系表",
        "knowledge_relations": "知识关系表",
        "knowledge_links": "旧版条目关系表",
    }
    issues: list[str] = []
    suggestions: list[str] = []
    counts = {
        "item_count": 0,
        "concept_count": 0,
        "relation_count": 0,
        "link_count": 0,
        "fts_row_count": 0,
        "graph_node_count": 0,
        "graph_edge_count": 0,
    }
    tables: dict[str, bool] = {name: False for name in required_tables}
    fts_ok = False
    db_readable = False
    last_error = ""
    try:
        with connect() as conn:
            db_readable = True
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual table')"
            ).fetchall()
            existing = {str(row["name"]) for row in rows}
            tables = {name: name in existing for name in required_tables}
            missing = [label for name, label in required_tables.items() if name not in existing]
            if missing:
                issues.append("本地知识库结构不完整: " + "、".join(missing))
                suggestions.append("重启情报台让本地数据库自动迁移；若仍异常，可运行云端 reindex 重建本地索引。")
            if tables["intel_items"]:
                counts["item_count"] = int(conn.execute("SELECT COUNT(*) AS c FROM intel_items").fetchone()["c"])
            if tables["knowledge_concepts"]:
                counts["concept_count"] = int(
                    conn.execute("SELECT COUNT(*) AS c FROM knowledge_concepts").fetchone()["c"]
                )
            if tables["knowledge_relations"]:
                counts["relation_count"] = int(
                    conn.execute("SELECT COUNT(*) AS c FROM knowledge_relations").fetchone()["c"]
                )
            if tables["knowledge_links"]:
                counts["link_count"] = int(conn.execute("SELECT COUNT(*) AS c FROM knowledge_links").fetchone()["c"])
            if tables["intel_fts"]:
                try:
                    counts["fts_row_count"] = int(conn.execute("SELECT COUNT(*) AS c FROM intel_fts").fetchone()["c"])
                    conn.execute("SELECT item_id FROM intel_fts LIMIT 1").fetchone()
                    fts_ok = True
                except sqlite3.Error as exc:
                    last_error = str(exc)
                    issues.append("全文检索索引不可读。")
                    suggestions.append("请运行 cloud reindex 或重新收录/同步知识库以重建 FTS 索引。")
            counts["graph_node_count"] = counts["item_count"] + counts["concept_count"]
            counts["graph_edge_count"] = counts["relation_count"] + counts["link_count"]
    except sqlite3.Error as exc:
        last_error = str(exc)
        issues.append("本地 SQLite 知识库暂时不可读。")
        suggestions.append("请确认没有把 knowledge.db 放进 OneDrive 网络同步目录；必要时从 Markdown vault 重新索引。")
    if db_readable and counts["item_count"] == 0:
        suggestions.append("知识库还是空的。可以先在搜索结果里批量收录，或在收录页保存 URL。")
    if db_readable and counts["item_count"] > 0 and tables.get("intel_fts") and counts["fts_row_count"] == 0:
        issues.append("已有条目，但全文索引为空。")
        suggestions.append("请执行知识库重建索引，或从云端 vault reindex。")
    return {
        "ok": db_readable and not issues,
        "db_readable": db_readable,
        "db_path": str(db_path),
        "fts_ok": fts_ok,
        "tables": tables,
        "issues": issues,
        "suggestions": list(dict.fromkeys(suggestions)),
        "last_error": last_error,
        **counts,
    }


def list_items(
    *,
    query: str = "",
    source: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[IntelItem]:
    conn = connect()
    try:
        sql = "SELECT data_json, created_at FROM intel_items WHERE 1=1"
        params: list[Any] = []
        if query:
            sql += " AND (title LIKE ? OR content LIKE ?)"
            params.extend([f"%{query}%", f"%{query}%"])
        if source:
            sql += " AND source = ?"
            params.append(source)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    items = []
    for row in rows:
        try:
            item = IntelItem.from_dict(json.loads(row["data_json"]))
        except (json.JSONDecodeError, TypeError):
            continue
        item.personal["saved_at"] = row["created_at"]
        items.append(item)
    return items


def get_item_links(item_id: str, *, limit: int = 12) -> list[dict[str, Any]]:
    return knowledge_search.get_item_links(item_id, limit=limit)


def enrich_item(item_id: str, *, use_ai: bool = False) -> dict[str, Any]:
    return knowledge_graph.enrich_item(item_id, use_ai=use_ai)


def graph(
    *,
    item_id: str | None = None,
    relation: str | None = None,
    min_confidence: float = 0.0,
    limit: int = 200,
) -> dict[str, Any]:
    return knowledge_graph.get_graph(
        item_id=item_id,
        relation=relation,
        min_confidence=min_confidence,
        limit=limit,
    )


def list_concepts(*, query: str = "", kind: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    return knowledge_graph.list_concepts(query=query, kind=kind, limit=limit)


def get_concept(name: str, *, limit: int = 80) -> dict[str, Any]:
    return knowledge_graph.get_concept(name, limit=limit)


def research_questions(
    *,
    item_id: str | None = None,
    topic: str | None = None,
    query: str | None = None,
    limit: int = 8,
) -> dict[str, Any]:
    return knowledge_graph.research_questions(item_id=item_id, topic=topic, query=query, limit=limit)


def count_items(source: str | None = None) -> int:
    conn = connect()
    try:
        if source:
            row = conn.execute("SELECT COUNT(*) AS c FROM intel_items WHERE source = ?", (source,)).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) AS c FROM intel_items").fetchone()
    finally:
        conn.close()
    return int(row["c"]) if row else 0


def delete_item(item_id: str) -> bool:
    """删除单条知识库条目。返回是否成功删除。"""
    return _delete_item(item_id)


def delete_items(item_ids: list[str]) -> int:
    """批量删除知识库条目。返回实际删除条数。"""
    return _delete_items(item_ids)


def list_topics(limit: int = 50) -> list[dict[str, Any]]:
    """聚合最近知识库条目的 topics 字段，按出现频率排序返回。"""
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT data_json FROM intel_items ORDER BY created_at DESC LIMIT 5000"
        ).fetchall()
    finally:
        conn.close()
    counter: dict[str, int] = {}
    for row in rows:
        try:
            data = json.loads(row["data_json"])
            for topic in data.get("topics") or []:
                if isinstance(topic, str) and topic:
                    counter[topic] = counter.get(topic, 0) + 1
        except (json.JSONDecodeError, TypeError):
            continue
    sorted_topics = sorted(counter.items(), key=lambda x: -x[1])
    return [{"topic": t, "count": c} for t, c in sorted_topics[:limit]]


def list_filters(limit: int = 50) -> dict[str, list[dict[str, Any]]]:
    conn = connect()
    try:
        rows = conn.execute("SELECT data_json FROM intel_items ORDER BY created_at DESC LIMIT 5000").fetchall()
    finally:
        conn.close()
    source_counts: dict[str, int] = {}
    topic_counts: dict[str, int] = {}
    entity_counts: dict[str, int] = {}
    tag_counts: dict[str, int] = {}
    capture_counts: dict[str, int] = {}
    for row in rows:
        try:
            data = json.loads(row["data_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        source = str(data.get("source") or "")
        if source:
            source_counts[source] = source_counts.get(source, 0) + 1
        for topic in data.get("topics") or []:
            if isinstance(topic, str) and topic:
                topic_counts[topic] = topic_counts.get(topic, 0) + 1
        for entity in extract_entities_from_payload(data):
            entity_counts[entity] = entity_counts.get(entity, 0) + 1
        for tag in extract_tags_from_payload(data):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
        capture_reason = str((data.get("personal") or {}).get("capture_reason") or "")
        if capture_reason:
            capture_counts[capture_reason] = capture_counts.get(capture_reason, 0) + 1
    def _top(counter: dict[str, int]) -> list[dict[str, Any]]:
        pairs = sorted(counter.items(), key=lambda pair: (-pair[1], pair[0]))[:limit]
        return [{"value": key, "count": count} for key, count in pairs]

    return {
        "sources": _top(source_counts),
        "topics": _top(topic_counts),
        "entities": _top(entity_counts),
        "tags": _top(tag_counts),
        "capture_reasons": _top(capture_counts),
    }
