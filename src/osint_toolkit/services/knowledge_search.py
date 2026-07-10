"""Hybrid knowledge search with explainable ranking."""

from __future__ import annotations

import json
import math
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from osint_toolkit.feedback.signals import build_feedback_profile
from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.persona.behavior_signals import score_event
from osint_toolkit.storage.knowledge_index import (
    build_search_document_from_payload,
    extract_entities_from_payload,
    extract_tags_from_payload,
)
from osint_toolkit.storage.sqlite import connect

_QUERY_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{1,8}|[a-zA-Z0-9][a-zA-Z0-9_.+-]{1,}")
_MAX_CANDIDATES = 180
_PURE_CJK_RE = re.compile(r"^[\u4e00-\u9fff]+$")


def _parse_when(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed
    except (ValueError, TypeError):
        return None


def _temporal_decay(created_at_str: str | None, half_life_days: float = 30.0) -> float:
    created = _parse_when(created_at_str)
    if created is None:
        return 0.5
    age_days = (datetime.now(UTC) - created).total_seconds() / 86400
    return math.pow(0.5, age_days / half_life_days)


def _terms(query: str) -> list[str]:
    q = str(query or "").strip()
    if not q:
        return []
    expanded: list[str] = [q]
    for token in _QUERY_TOKEN_RE.findall(q):
        expanded.append(token)
        if _PURE_CJK_RE.fullmatch(token) and len(token) > 4:
            for size in (4, 3, 2):
                for idx in range(0, len(token) - size + 1):
                    expanded.append(token[idx : idx + size])
    out: list[str] = []
    seen: set[str] = set()
    for token in expanded:
        value = token.strip()
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _query_variants(query: str) -> list[str]:
    variants: list[str] = []
    seen: set[str] = set()
    for token in _terms(query):
        value = token.strip()
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        variants.append(value)
    return variants[:12]


def _fts_query(query: str) -> str:
    ranked_terms = sorted(
        enumerate(_terms(query)),
        key=lambda pair: (
            0 if len(pair[1]) > 10 and _PURE_CJK_RE.fullmatch(pair[1]) else 1,
            2 if _PURE_CJK_RE.fullmatch(pair[1] or "") and 2 <= len(pair[1]) <= 4 else 1,
            1 if re.search(r"[a-zA-Z0-9]", pair[1]) else 0,
            min(len(pair[1]), 12),
            -pair[0],
        ),
        reverse=True,
    )
    clauses: list[str] = []
    for _idx, token in ranked_terms[:8]:
        escaped = token.replace('"', '""')
        clauses.append(f'"{escaped}"')
    return " OR ".join(clauses)


def _item_from_row(row: Any) -> IntelItem | None:
    try:
        data = json.loads(row["data_json"])
    except (json.JSONDecodeError, TypeError, KeyError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        item = IntelItem.from_dict(data)
    except Exception:  # noqa: BLE001
        return None
    saved_at = str(row["created_at"] or "")
    if saved_at and not item.personal.get("saved_at"):
        item.personal["saved_at"] = saved_at
    if row["vault_status"]:
        item.personal["vault_status"] = str(row["vault_status"])
    if row["vault_path"]:
        item.personal["vault_path"] = str(row["vault_path"])
    if int(row["conflict_count"] or 0) > 0:
        item.personal["vault_conflict"] = True
    return item


def _load_fts_candidates(
    query: str,
    *,
    source: str | None = None,
    limit: int = _MAX_CANDIDATES,
) -> list[dict[str, Any]]:
    fts_query = _fts_query(query)
    if not fts_query:
        return []
    conn = connect()
    try:
        sql = """
            SELECT
                i.data_json,
                i.created_at,
                v.status AS vault_status,
                v.vault_path AS vault_path,
                v.conflict_count AS conflict_count,
                bm25(intel_fts, 12.0, 4.0, 3.0, 6.0, 2.0) AS bm25_score
            FROM intel_fts
            JOIN intel_items i ON i.id = intel_fts.item_id
            LEFT JOIN vault_sync_state v ON v.item_id = i.id
            WHERE intel_fts MATCH ?
        """
        params: list[Any] = [fts_query]
        if source:
            sql += " AND i.source = ?"
            params.append(source)
        sql += " ORDER BY bm25_score LIMIT ?"
        params.append(max(20, min(int(limit), 500)))
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = _item_from_row(row)
        if item is None:
            continue
        out.append({"item": item, "bm25": float(row["bm25_score"] or 0.0), "origin": "fts"})
    return out


def _load_like_candidates(
    query: str,
    *,
    source: str | None = None,
    limit: int = _MAX_CANDIDATES,
) -> list[dict[str, Any]]:
    q = str(query or "").strip()
    if not q:
        return []
    conn = connect()
    try:
        sql = """
            SELECT
                i.data_json,
                i.created_at,
                v.status AS vault_status,
                v.vault_path AS vault_path,
                v.conflict_count AS conflict_count
            FROM intel_items i
            LEFT JOIN vault_sync_state v ON v.item_id = i.id
            WHERE (i.title LIKE ? OR i.content LIKE ? OR i.data_json LIKE ?)
        """
        params: list[Any] = [f"%{q}%", f"%{q}%", f"%{q}%"]
        if source:
            sql += " AND i.source = ?"
            params.append(source)
        sql += " ORDER BY i.created_at DESC LIMIT ?"
        params.append(max(20, min(int(limit), 500)))
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = _item_from_row(row)
        if item is None:
            continue
        out.append({"item": item, "bm25": None, "origin": "like"})
    return out


def _load_concept_candidates(
    query: str,
    *,
    source: str | None = None,
    limit: int = _MAX_CANDIDATES,
) -> list[dict[str, Any]]:
    terms = _query_variants(query)
    if not terms:
        return []
    conditions = []
    params: list[Any] = []
    for term in terms[:8]:
        conditions.append("(kc.name LIKE ? OR kc.summary LIKE ?)")
        params.extend([f"%{term}%", f"%{term}%"])
    conn = connect()
    try:
        source_clause = " AND i.source = ?" if source else ""
        rows = conn.execute(
            f"""
            SELECT
                i.data_json,
                i.created_at,
                v.status AS vault_status,
                v.vault_path AS vault_path,
                v.conflict_count AS conflict_count,
                c.concept_name,
                c.kind,
                c.confidence,
                c.evidence
            FROM knowledge_concepts kc
            JOIN knowledge_item_concepts c ON c.concept_name = kc.name
            JOIN intel_items i ON i.id = c.item_id
            LEFT JOIN vault_sync_state v ON v.item_id = i.id
            WHERE ({' OR '.join(conditions)}){source_clause}
            ORDER BY c.confidence DESC, i.created_at DESC
            LIMIT ?
            """,
            [*params, *([source] if source else []), max(20, min(int(limit), 500))],
        ).fetchall()
    finally:
        conn.close()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = _item_from_row(row)
        if item is None:
            continue
        out.append(
            {
                "item": item,
                "bm25": None,
                "origin": "concept",
                "concept_name": str(row["concept_name"] or ""),
                "concept_kind": str(row["kind"] or "concept"),
                "concept_confidence": float(row["confidence"] or 0.0),
                "concept_evidence": str(row["evidence"] or ""),
            }
        )
    return out


def _load_behavior_hits(query: str, *, limit: int = 24) -> list[dict[str, Any]]:
    q = str(query or "").strip()
    if not q:
        return []
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT event_type, data_json, created_at FROM events WHERE data_json LIKE ? ORDER BY id DESC LIMIT ?",
            (f"%{q}%", max(10, min(int(limit), 200))),
        ).fetchall()
    finally:
        conn.close()
    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            data = json.loads(row["data_json"] or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        if score_event(str(row["event_type"] or ""), data) < 12:
            continue
        item = IntelItem(
            source=str(data.get("source") or "behavior"),
            type="behavior",
            url=str(data.get("url") or ""),
            title=str(data.get("title") or data.get("url") or row["event_type"] or "行为证据"),
            content=str(data.get("content") or ""),
            summary=f"行为证据: {row['event_type']}",
            personal={
                "from": "events",
                "event_type": str(row["event_type"] or ""),
                "saved_at": str(row["created_at"] or ""),
                "dwell_sec": int(int(data.get("duration_ms") or 0) / 1000),
            },
        )
        out.append({"item": item, "bm25": None, "origin": "behavior"})
    return out


def _clip(text: str, limit: int = 180) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "..."


def _build_snippets(item: IntelItem, query: str, *, limit: int = 2) -> list[str]:
    snippets: list[str] = []
    terms = _terms(query)
    sources = [item.summary, " ".join(item.key_points or []), item.content]
    for source in sources:
        text = str(source or "").strip()
        if not text:
            continue
        lower = text.casefold()
        best = -1
        best_len = 0
        for term in terms:
            idx = lower.find(term.casefold())
            if idx >= 0 and (best < 0 or idx < best):
                best = idx
                best_len = len(term)
        if best < 0:
            continue
        start = max(0, best - 48)
        end = min(len(text), best + max(best_len, 18) + 72)
        snippet = text[start:end].strip()
        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet += "..."
        snippets.append(_clip(snippet, 220))
        if len(snippets) >= limit:
            break
    return snippets


def _rating_polarity(rating: str) -> int:
    low = str(rating or "").strip().lower()
    if low in {"useful", "helpful", "interested", "good"}:
        return 1
    if low in {"noise", "wrong", "skip", "bad", "not_useful"}:
        return -1
    return 0


def _feedback_delta(item: IntelItem, profile: Any) -> tuple[float, list[str]]:
    if not getattr(profile, "feedback_count", 0):
        return 0.0, []
    delta = 0.0
    reasons: list[str] = []
    if item.url and item.url in profile.url_ratings:
        polarity = _rating_polarity(profile.url_ratings[item.url])
        if polarity > 0:
            delta += 0.14
            reasons.append("历史反馈: 同 URL 曾被标记有用")
        elif polarity < 0:
            delta -= 0.18
            reasons.append("历史反馈: 同 URL 曾被标记噪音")
    source_score = profile.source_scores.get(f"source:{item.source}", 0)
    if source_score >= 3:
        delta += 0.03
        reasons.append("历史反馈: 该来源近期命中率较高")
    elif source_score <= -3:
        delta -= 0.03
        reasons.append("历史反馈: 该来源近期噪音率较高")
    host = urlparse(item.url).netloc.lower() if item.url else ""
    host_score = profile.source_scores.get(f"host:{host}", 0) if host else 0
    if host_score >= 2:
        delta += 0.03
        reasons.append("历史反馈: 该站点近期命中率较高")
    elif host_score <= -2:
        delta -= 0.03
        reasons.append("历史反馈: 该站点近期噪音率较高")
    return delta, reasons


def _passes_filters(
    item: IntelItem,
    *,
    source: str | None = None,
    topic: str | None = None,
    tag: str | None = None,
    entity: str | None = None,
    run_id: str | None = None,
    capture_reason: str | None = None,
    conflict_status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> bool:
    if source and item.source != source:
        return False
    if topic and topic not in (item.topics or []):
        return False
    tags = extract_tags_from_payload(item.model_dump())
    if tag and tag not in tags:
        return False
    entities = extract_entities_from_payload(item.model_dump())
    if entity and entity not in entities:
        return False
    if run_id and str(item.personal.get("run_id") or "") != str(run_id):
        return False
    if capture_reason and str(item.personal.get("capture_reason") or "") != str(capture_reason):
        return False
    if conflict_status == "only" and not bool(item.personal.get("vault_conflict")):
        return False
    if conflict_status == "clean" and bool(item.personal.get("vault_conflict")):
        return False
    start = _parse_when(date_from)
    end = _parse_when(date_to)
    saved = _parse_when(item.personal.get("saved_at") or item.published_at)
    if start and saved and saved < start:
        return False
    if end and saved and saved > end:
        return False
    if (start or end) and saved is None:
        return False
    return True


def _score_item(
    item: IntelItem,
    *,
    query: str,
    bm25_score: float | None,
    origin: str,
    feedback_profile: Any,
) -> tuple[float, dict[str, float], list[str], list[str]]:
    q = str(query or "").strip()
    q_low = q.casefold()
    doc = build_search_document_from_payload(item.model_dump())
    title = doc["title"]
    content = doc["content"]
    summary = doc["summary"]
    keywords = doc["keywords"]
    meta = doc["meta"]
    title_low = title.casefold()
    content_low = content.casefold()
    summary_low = summary.casefold()
    keyword_low = keywords.casefold()
    meta_low = meta.casefold()
    haystack = " ".join([title_low, summary_low, content_low, keyword_low, meta_low])
    matched_terms = [term for term in _terms(query) if term.casefold() in haystack]

    parts: dict[str, float] = {}
    reasons: list[str] = []
    if q_low and q_low in title_low:
        parts["title"] = 0.42
        reasons.append("标题直接命中查询")
    if q_low and q_low in summary_low:
        parts["summary"] = max(parts.get("summary", 0.0), 0.18)
        reasons.append("摘要命中查询")
    if q_low and q_low in content_low:
        parts["content"] = max(parts.get("content", 0.0), 0.12)
        reasons.append("正文命中查询")
    if q_low and q_low in keyword_low:
        parts["knowledge_fields"] = max(parts.get("knowledge_fields", 0.0), 0.2)
        reasons.append("主题/实体/标签命中")
    if q_low and q_low in meta_low:
        parts["meta"] = max(parts.get("meta", 0.0), 0.08)
        reasons.append("元数据命中")
    if matched_terms:
        coverage = min(1.0, len(matched_terms) / max(1, len(_terms(query))))
        parts["coverage"] = round(coverage * 0.16, 4)
        if coverage >= 0.75:
            reasons.append("查询词覆盖度高")
    if origin == "fts":
        bm25_part = 0.1 if bm25_score is None else max(0.04, min(0.16, 0.18 / (1.0 + max(float(bm25_score), 0.0))))
        parts["fts"] = round(bm25_part, 4)
    elif origin == "behavior":
        parts["behavior_match"] = 0.12
        reasons.append("行为证据命中")
    else:
        parts["keyword"] = 0.06
    if origin == "concept":
        parts["concept_recall"] = max(parts.get("concept_recall", 0.0), 0.13)
        reasons.append("相关概念/实体/项目召回")

    decay = _temporal_decay(item.personal.get("saved_at") or item.published_at)
    parts["freshness"] = round(decay * 0.08, 4)

    dwell_sec = float(item.personal.get("dwell_sec") or 0.0)
    if dwell_sec > 0:
        parts["dwell"] = round(min(0.08, dwell_sec / 900.0 * 0.08), 4)
        reasons.append("高停留时长")

    capture_reason = str(item.personal.get("capture_reason") or "")
    if capture_reason == "manual_save":
        parts["capture_reason"] = 0.05
        reasons.append("手动收录")
    elif capture_reason == "run_batch":
        parts["capture_reason"] = 0.03
    elif capture_reason == "dwell_auto":
        parts["capture_reason"] = 0.04
        reasons.append("自动收录行为证据")

    feedback_delta, feedback_reasons = _feedback_delta(item, feedback_profile)
    if abs(feedback_delta) > 0.001:
        parts["feedback"] = round(feedback_delta, 4)
        reasons.extend(feedback_reasons)

    if bool(item.personal.get("vault_conflict")):
        parts["conflict"] = -0.03
        reasons.append("该笔记存在待合并冲突副本")

    snippets = _build_snippets(item, query)
    score = round(sum(parts.values()), 4)
    if not snippets and item.summary:
        snippets = [_clip(item.summary, 220)]
    elif not snippets and item.content:
        snippets = [_clip(item.content, 220)]
    return score, parts, reasons, snippets


def _serialize_hit(
    item: IntelItem,
    *,
    score: float,
    score_parts: dict[str, float],
    reasons: list[str],
    snippets: list[str],
    match_type: str,
) -> dict[str, Any]:
    return {
        "item": item,
        "score": round(score, 4),
        "score_parts": score_parts,
        "match_reasons": reasons,
        "snippets": snippets,
        "match_type": match_type,
        "concepts": _concepts_for_item(item.id),
        "project": _project_for_item(item),
    }


def _relation_label(relation: str) -> str:
    return {
        "same_topic": "同主题",
        "same_entity": "同实体",
        "supports": "支持",
        "contradicts": "冲突",
        "explains": "解释",
        "extends": "延伸",
        "duplicate_of": "近似重复",
        "source_of": "来源依据",
        "mentions_entity": "提到实体",
        "belongs_to_project": "所属项目",
    }.get(relation, relation or "关联")


def _concepts_for_item(item_id: str, *, limit: int = 8) -> list[dict[str, Any]]:
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT concept_name, kind, confidence, evidence
            FROM knowledge_item_concepts
            WHERE item_id = ?
            ORDER BY confidence DESC, updated_at DESC
            LIMIT ?
            """,
            (item_id, max(1, min(int(limit), 30))),
        ).fetchall()
    except Exception:  # noqa: BLE001
        return []
    finally:
        conn.close()
    return [
        {
            "name": str(row["concept_name"] or ""),
            "kind": str(row["kind"] or "concept"),
            "confidence": float(row["confidence"] or 0.0),
            "evidence": str(row["evidence"] or ""),
        }
        for row in rows
        if row["concept_name"]
    ]


def _project_for_item(item: IntelItem) -> str:
    personal = item.personal or {}
    project = personal.get("project") or personal.get("active_project")
    if project:
        return str(project)
    for concept in _concepts_for_item(item.id, limit=12):
        if concept.get("kind") == "project":
            return str(concept.get("name") or "")
    return ""


def get_item_links(item_id: str, *, limit: int = 12) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 50))
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT
                l.from_item_id,
                l.to_item_id,
                l.relation,
                l.confidence,
                l.evidence,
                i.data_json,
                i.created_at,
                v.status AS vault_status,
                v.vault_path AS vault_path,
                v.conflict_count AS conflict_count
            FROM knowledge_links l
            JOIN intel_items i
                ON i.id = CASE WHEN l.from_item_id = ? THEN l.to_item_id ELSE l.from_item_id END
            LEFT JOIN vault_sync_state v ON v.item_id = i.id
            WHERE l.from_item_id = ? OR l.to_item_id = ?
            ORDER BY l.confidence DESC, i.created_at DESC
            LIMIT ?
            """,
            (item_id, item_id, item_id, safe_limit),
        ).fetchall()
    finally:
        conn.close()
    links: list[dict[str, Any]] = []
    for row in rows:
        item = _item_from_row(row)
        if item is None:
            continue
        links.append(
            {
                "item": item,
                "relation": str(row["relation"] or ""),
                "relation_label": _relation_label(str(row["relation"] or "")),
                "confidence": float(row["confidence"] or 0.0),
                "evidence": str(row["evidence"] or ""),
            }
        )
    return links


def _expand_graph_hits(
    direct_hits: list[dict[str, Any]],
    *,
    limit: int,
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    if not direct_hits or limit <= 0:
        return []
    seed_ids = [hit["item"].id for hit in direct_hits[: min(8, len(direct_hits))]]
    conn = connect()
    try:
        placeholders = ",".join("?" for _ in seed_ids)
        link_rows = conn.execute(
            f"""
            SELECT
                l.from_item_id,
                l.to_item_id,
                l.relation,
                l.confidence,
                l.evidence,
                i.data_json,
                i.created_at,
                v.status AS vault_status,
                v.vault_path AS vault_path,
                v.conflict_count AS conflict_count
            FROM knowledge_links l
            JOIN intel_items i
                ON i.id = CASE
                    WHEN l.from_item_id IN ({placeholders}) THEN l.to_item_id
                    ELSE l.from_item_id
                END
            LEFT JOIN vault_sync_state v ON v.item_id = i.id
            WHERE l.from_item_id IN ({placeholders}) OR l.to_item_id IN ({placeholders})
            ORDER BY l.confidence DESC, i.created_at DESC
            LIMIT ?
            """,
            [*seed_ids, *seed_ids, *seed_ids, max(20, min(limit * 8, 120))],
        ).fetchall()
        relation_rows = conn.execute(
            f"""
            SELECT
                r.from_id AS from_item_id,
                r.to_id AS to_item_id,
                r.relation,
                r.confidence,
                r.evidence,
                i.data_json,
                i.created_at,
                v.status AS vault_status,
                v.vault_path AS vault_path,
                v.conflict_count AS conflict_count
            FROM knowledge_relations r
            JOIN intel_items i
                ON i.id = CASE
                    WHEN r.from_id IN ({placeholders}) THEN r.to_id
                    ELSE r.from_id
                END
            LEFT JOIN vault_sync_state v ON v.item_id = i.id
            WHERE r.from_type = 'item'
              AND r.to_type = 'item'
              AND (r.from_id IN ({placeholders}) OR r.to_id IN ({placeholders}))
              AND COALESCE(r.status, '') != 'rejected'
            ORDER BY r.confidence DESC, r.created_at DESC
            LIMIT ?
            """,
            [*seed_ids, *seed_ids, *seed_ids, max(20, min(limit * 8, 120))],
        ).fetchall()
    finally:
        conn.close()
    seed_scores = {hit["item"].id: float(hit["score"]) for hit in direct_hits}
    existing_ids = {hit["item"].id for hit in direct_hits}
    grouped: dict[str, dict[str, Any]] = {}
    for row in [*link_rows, *relation_rows]:
        item = _item_from_row(row)
        if item is None or item.id in existing_ids:
            continue
        if not _passes_filters(item, **filters):
            continue
        source_id = str(row["from_item_id"] or "")
        target_id = str(row["to_item_id"] or "")
        seed_id = source_id if source_id in seed_scores else target_id if target_id in seed_scores else ""
        if not seed_id:
            continue
        relation = str(row["relation"] or "")
        score = round(seed_scores.get(seed_id, 0.18) * 0.32 + float(row["confidence"] or 0.0) * 0.18, 4)
        reason = f"{_relation_label(relation)}关联"
        evidence = str(row["evidence"] or "")
        if evidence:
            reason += f": {evidence}"
        payload = grouped.get(item.id)
        if payload is None or score > payload["score"]:
            snippets = [_clip(item.summary or item.content, 220)] if (item.summary or item.content) else []
            grouped[item.id] = _serialize_hit(
                item,
                score=score,
                score_parts={"graph": score},
                reasons=[reason],
                snippets=snippets,
                match_type="graph",
            )
    return sorted(
        grouped.values(),
        key=lambda hit: (hit["score"], hit["item"].personal.get("saved_at") or ""),
        reverse=True,
    )[:limit]


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
    q = str(query or "").strip()
    if not q:
        return []
    safe_limit = max(1, min(int(limit), 200))
    filter_kwargs = {
        "source": source,
        "topic": topic,
        "tag": tag,
        "entity": entity,
        "run_id": run_id,
        "capture_reason": capture_reason,
        "conflict_status": conflict_status,
        "date_from": date_from,
        "date_to": date_to,
    }
    candidates: list[dict[str, Any]] = []
    if mode in {"hybrid", "fts", "semantic"}:
        for variant in _query_variants(q)[:5]:
            candidates.extend(_load_fts_candidates(variant, source=source, limit=max(40, safe_limit * 4)))
    if mode in {"hybrid", "keyword"}:
        for variant in _query_variants(q)[:8]:
            candidates.extend(_load_like_candidates(variant, source=source, limit=max(40, safe_limit * 4)))
    if mode == "hybrid":
        candidates.extend(_load_concept_candidates(q, source=source, limit=max(40, safe_limit * 4)))
        candidates.extend(_load_behavior_hits(q, limit=min(24, safe_limit * 2)))

    feedback_profile = build_feedback_profile()
    by_id: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        item = candidate["item"]
        if item.id in by_id and candidate["origin"] != "fts":
            continue
        if not _passes_filters(item, **filter_kwargs):
            continue
        score, score_parts, reasons, snippets = _score_item(
            item,
            query=q,
            bm25_score=candidate.get("bm25"),
            origin=str(candidate.get("origin") or ""),
            feedback_profile=feedback_profile,
        )
        if score <= 0.02:
            continue
        hit = _serialize_hit(
            item,
            score=score,
            score_parts=score_parts if explain else {},
            reasons=reasons if explain else reasons[:3],
            snippets=snippets,
            match_type=(
                "behavior"
                if candidate.get("origin") == "behavior"
                else "concept"
                if candidate.get("origin") == "concept"
                else "direct"
            ),
        )
        if candidate.get("origin") == "concept" and candidate.get("concept_name"):
            hit["match_reasons"] = [
                *hit.get("match_reasons", []),
                f"{_relation_label('mentions_entity')}: {candidate['concept_name']}",
            ]
        prev = by_id.get(item.id)
        if prev is None or float(hit["score"]) > float(prev["score"]):
            by_id[item.id] = hit

    direct_hits = sorted(
        by_id.values(),
        key=lambda hit: (float(hit["score"]), hit["item"].personal.get("saved_at") or ""),
        reverse=True,
    )[:safe_limit]

    if not include_related or len(direct_hits) >= safe_limit:
        return direct_hits[:safe_limit]

    graph_hits = _expand_graph_hits(direct_hits, limit=safe_limit - len(direct_hits), filters=filter_kwargs)
    return [*direct_hits, *graph_hits][:safe_limit]


def suggest(query: str, *, limit: int = 8) -> dict[str, Any]:
    terms = _query_variants(query)
    keywords = [term for term in terms if len(term) >= 2][:limit]
    concepts: list[dict[str, Any]] = []
    if terms:
        conn = connect()
        try:
            conditions = []
            params: list[Any] = []
            for term in terms[:6]:
                conditions.append("(name LIKE ? OR summary LIKE ?)")
                params.extend([f"%{term}%", f"%{term}%"])
            rows = conn.execute(
                f"""
                SELECT name, kind, item_count
                FROM knowledge_concepts
                WHERE {' OR '.join(conditions)}
                ORDER BY item_count DESC, updated_at DESC
                LIMIT ?
                """,
                [*params, max(1, min(int(limit), 20))],
            ).fetchall()
            concepts = [
                {
                    "name": str(row["name"] or ""),
                    "kind": str(row["kind"] or "concept"),
                    "item_count": int(row["item_count"] or 0),
                }
                for row in rows
                if row["name"]
            ]
        except Exception:  # noqa: BLE001
            concepts = []
        finally:
            conn.close()
    questions = []
    seed = keywords[0] if keywords else str(query or "").strip()
    if seed:
        questions = [
            f"{seed} 的关键概念有哪些？",
            f"{seed} 还有哪些未覆盖的来源？",
            f"{seed} 是否和已有观点存在冲突？",
        ]
    return {
        "keywords": keywords,
        "concepts": concepts,
        "follow_up_questions": questions[:limit],
    }
