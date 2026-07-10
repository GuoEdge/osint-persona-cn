"""Knowledge graph enrichment and graph queries."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.services import knowledge_search
from osint_toolkit.storage.knowledge import save_item
from osint_toolkit.storage.knowledge_index import (
    as_str_list,
    extract_entities_from_payload,
    unique_texts,
)
from osint_toolkit.storage.sqlite import connect

_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,8}|[a-zA-Z][a-zA-Z0-9_.+-]{2,}")
_QUESTION_RE = re.compile(r"([^。！？!?；;\n]{2,120}[？?])")
_SENTENCE_SPLIT_RE = re.compile(r"[。！？!?；;\n]+")
_MAX_CONCEPTS = 24
_MAX_RELATIONS = 80


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _clip(text: Any, limit: int = 180) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "..."


def _relation_id(
    *,
    from_type: str,
    from_id: str,
    relation: str,
    to_type: str,
    to_id: str,
    source: str,
) -> str:
    raw = f"{from_type}:{from_id}|{relation}|{to_type}:{to_id}|{source}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _concept_key(name: str) -> str:
    return str(name or "").strip()


def _tokens(text: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for token in _TOKEN_RE.findall(text or ""):
        value = token.strip()
        if len(value) < 2:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _claim_candidates(item: IntelItem) -> list[str]:
    claims: list[str] = []
    claims.extend(as_str_list(item.personal.get("claims")))
    claims.extend(as_str_list((item.layers or {}).get("claims")))
    claims.extend(as_str_list(item.key_points))
    summary = str(item.summary or "").strip()
    if summary:
        for sentence in _SENTENCE_SPLIT_RE.split(summary):
            sentence = sentence.strip()
            if 8 <= len(sentence) <= 140:
                claims.append(sentence)
    return unique_texts([_clip(c, 160) for c in claims])[:8]


def _question_candidates(item: IntelItem) -> list[str]:
    questions: list[str] = []
    questions.extend(as_str_list(item.personal.get("questions")))
    questions.extend(as_str_list((item.layers or {}).get("questions")))
    text = "\n".join([item.title or "", item.summary or "", item.content or ""])
    for match in _QUESTION_RE.findall(text):
        questions.append(match.strip())
    if not questions and any(word in text for word in ("如何", "为什么", "怎么", "是否")):
        questions.append(f"围绕「{_clip(item.title, 60)}」还需要核查什么？")
    return unique_texts([_clip(q, 160) for q in questions])[:8]


def extract_item_knowledge(item: IntelItem) -> dict[str, Any]:
    payload = item.model_dump()
    topics = unique_texts(as_str_list(item.topics))[:12]
    entities = unique_texts(extract_entities_from_payload(payload))[:18]
    explicit_concepts = as_str_list(item.personal.get("concepts"))
    explicit_concepts.extend(as_str_list((item.layers or {}).get("concepts")))
    source_text = " ".join([item.title or "", item.summary or "", " ".join(item.key_points or [])])
    concepts = unique_texts([*explicit_concepts, *_tokens(source_text)])[:_MAX_CONCEPTS]
    claims = _claim_candidates(item)
    questions = _question_candidates(item)
    project = _clip(item.personal.get("project") or item.personal.get("active_project") or "", 120)
    if not project and item.personal.get("run_id") and topics:
        project = topics[0]
    evidence_refs = unique_texts(
        [
            *as_str_list(item.personal.get("evidence_refs")),
            item.url,
            item.summary or item.content[:180],
        ]
    )[:8]
    confidence = float(item.personal.get("confidence") or item.signals.relevance or 0.65 or 0.0)
    confidence = max(0.1, min(confidence, 0.95))
    return {
        "topics": topics,
        "entities": entities,
        "concepts": concepts,
        "claims": claims,
        "questions": questions,
        "project": project,
        "confidence": confidence,
        "evidence_refs": evidence_refs,
    }


def _concept_records(extracted: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for topic in extracted["topics"]:
        records.append({"name": topic, "kind": "topic", "confidence": 0.85, "evidence": f"条目主题: {topic}"})
    for entity in extracted["entities"]:
        records.append({"name": entity, "kind": "entity", "confidence": 0.82, "evidence": f"条目实体: {entity}"})
    for concept in extracted["concepts"]:
        records.append(
            {"name": concept, "kind": "concept", "confidence": 0.68, "evidence": f"标题/摘要概念: {concept}"}
        )
    for claim in extracted["claims"]:
        records.append({"name": claim, "kind": "claim", "confidence": 0.62, "evidence": f"观点/要点: {claim}"})
    for question in extracted["questions"]:
        records.append({"name": question, "kind": "question", "confidence": 0.6, "evidence": f"待研究问题: {question}"})
    project = extracted.get("project") or ""
    if project:
        records.append({"name": project, "kind": "project", "confidence": 0.7, "evidence": f"研究项目: {project}"})
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for record in records:
        name = _concept_key(record["name"])
        if not name:
            continue
        key = (name.casefold(), str(record["kind"]))
        if key in seen:
            continue
        seen.add(key)
        record["name"] = name
        out.append(record)
    return out


def _relation_for_kind(kind: str) -> str:
    return {
        "topic": "extends",
        "entity": "mentions_entity",
        "concept": "explains",
        "claim": "source_of",
        "question": "extends",
        "project": "belongs_to_project",
    }.get(kind, "extends")


def _upsert_concept(conn: Any, record: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO knowledge_concepts (name, kind, summary, item_count, data_json, updated_at)
        VALUES (?, ?, ?, 0, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            kind = excluded.kind,
            summary = COALESCE(NULLIF(excluded.summary, ''), knowledge_concepts.summary),
            data_json = excluded.data_json,
            updated_at = excluded.updated_at
        """,
        (
            record["name"],
            record["kind"],
            record.get("summary") or "",
            json.dumps(record.get("data") or {}, ensure_ascii=False),
            _now(),
        ),
    )


def _upsert_item_concept(conn: Any, item_id: str, record: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO knowledge_item_concepts
        (item_id, concept_name, kind, confidence, status, evidence, data_json, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(item_id, concept_name, kind) DO UPDATE SET
            confidence = excluded.confidence,
            status = excluded.status,
            evidence = excluded.evidence,
            data_json = excluded.data_json,
            updated_at = excluded.updated_at
        """,
        (
            item_id,
            record["name"],
            record["kind"],
            float(record.get("confidence") or 0.0),
            record.get("status") or "confirmed",
            record.get("evidence") or record["name"],
            json.dumps(record.get("data") or {}, ensure_ascii=False),
            _now(),
        ),
    )


def _upsert_relation(
    conn: Any,
    *,
    from_type: str,
    from_id: str,
    to_type: str,
    to_id: str,
    relation: str,
    confidence: float,
    status: str,
    evidence: str,
    source: str = "rule",
    data: dict[str, Any] | None = None,
) -> None:
    rel_id = _relation_id(
        from_type=from_type,
        from_id=from_id,
        relation=relation,
        to_type=to_type,
        to_id=to_id,
        source=source,
    )
    conn.execute(
        """
        INSERT INTO knowledge_relations
        (id, from_type, from_id, to_type, to_id, relation, confidence, status, evidence, source, data_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            confidence = excluded.confidence,
            status = excluded.status,
            evidence = excluded.evidence,
            data_json = excluded.data_json
        """,
        (
            rel_id,
            from_type,
            from_id,
            to_type,
            to_id,
            relation,
            float(confidence),
            status,
            evidence,
            source,
            json.dumps(data or {}, ensure_ascii=False),
            _now(),
        ),
    )


def _refresh_concept_counts(conn: Any, names: list[str]) -> None:
    for name in unique_texts(names):
        row = conn.execute(
            "SELECT COUNT(DISTINCT item_id) AS c FROM knowledge_item_concepts WHERE concept_name = ?",
            (name,),
        ).fetchone()
        conn.execute(
            "UPDATE knowledge_concepts SET item_count = ?, updated_at = ? WHERE name = ?",
            (int(row["c"] or 0) if row else 0, _now(), name),
        )


def enrich_item_object(item: IntelItem, *, persist_item: bool = False) -> dict[str, Any]:
    extracted = extract_item_knowledge(item)
    records = _concept_records(extracted)
    item.personal["concepts"] = [record["name"] for record in records if record["kind"] == "concept"]
    item.personal["claims"] = extracted["claims"]
    item.personal["questions"] = extracted["questions"]
    if extracted["project"]:
        item.personal["project"] = extracted["project"]
    item.personal["confidence"] = extracted["confidence"]
    item.personal["evidence_refs"] = extracted["evidence_refs"]

    relation_summaries: list[dict[str, Any]] = []
    conn = connect()
    try:
        conn.execute("DELETE FROM knowledge_item_concepts WHERE item_id = ?", (item.id,))
        conn.execute(
            "DELETE FROM knowledge_relations WHERE source = 'rule' "
            "AND ((from_type = 'item' AND from_id = ?) OR (to_type = 'item' AND to_id = ?))",
            (item.id, item.id),
        )
        for record in records:
            _upsert_concept(conn, record)
            _upsert_item_concept(conn, item.id, record)
            relation = _relation_for_kind(record["kind"])
            _upsert_relation(
                conn,
                from_type="item",
                from_id=item.id,
                to_type=record["kind"],
                to_id=record["name"],
                relation=relation,
                confidence=float(record.get("confidence") or extracted["confidence"]),
                status=record.get("status") or "confirmed",
                evidence=record.get("evidence") or record["name"],
                source="rule",
                data={"item_title": item.title, "url": item.url},
            )
            relation_summaries.append(
                {
                    "from": item.id,
                    "to": record["name"],
                    "to_type": record["kind"],
                    "relation": relation,
                    "status": record.get("status") or "confirmed",
                    "confidence": float(record.get("confidence") or extracted["confidence"]),
                    "evidence": record.get("evidence") or record["name"],
                }
            )
        _refresh_concept_counts(conn, [record["name"] for record in records])
        conn.commit()
    finally:
        conn.close()
    item.personal["relations"] = relation_summaries[:_MAX_RELATIONS]
    if persist_item:
        save_item(item)
    return {
        "item_id": item.id,
        "concepts": records,
        "relations": relation_summaries,
        "extracted": extracted,
    }


def _lookup_concepts_by_names(names: list[str], *, kind: str | None = None, limit: int = 24) -> list[dict[str, Any]]:
    exact_names = unique_texts([_concept_key(name) for name in names if _concept_key(name)])
    if not exact_names:
        return []
    placeholders = ",".join("?" for _ in exact_names)
    sql = (
        "SELECT name, kind, summary, item_count, updated_at "
        f"FROM knowledge_concepts WHERE lower(name) IN ({placeholders})"
    )
    params: list[Any] = [name.casefold() for name in exact_names]
    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    sql += " ORDER BY item_count DESC, updated_at DESC LIMIT ?"
    params.append(max(1, min(int(limit), 200)))
    conn = connect()
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    return [
        {
            "name": row["name"],
            "kind": row["kind"],
            "summary": row["summary"] or "",
            "item_count": int(row["item_count"] or 0),
            "updated_at": row["updated_at"] or "",
        }
        for row in rows
    ]


def annotate_search_items(
    query: str,
    items: list[IntelItem],
    *,
    related_limit: int = 4,
    question_limit: int = 3,
    persona_structured: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Add read-only knowledge linkage hints to search results."""
    annotations: list[dict[str, Any]] = []
    linked_count = 0
    known_url_count = 0
    supplements_count = 0
    project_linked_count = 0
    concept_counter: dict[str, int] = {}
    project_counter: dict[str, int] = {}
    persona_domains = unique_texts(
        [
            str(row.get("name") or row)
            for row in ((persona_structured or {}).get("interest_domains") or [])
            if isinstance(row, (dict, str))
        ]
    )
    persona_projects = unique_texts(
        [
            str(row.get("name") or row)
            for row in ((persona_structured or {}).get("active_projects") or [])
            if isinstance(row, (dict, str))
        ]
    )
    persona_overlap_count = 0
    followup_count = 0

    for item in items:
        extracted = extract_item_knowledge(item)
        concept_hits = _lookup_concepts_by_names(
            [
                *(extracted.get("topics") or []),
                *(extracted.get("entities") or []),
                *(extracted.get("concepts") or []),
                *_tokens(item.content or "")[:6],
            ],
            limit=24,
        )
        project_hits = _lookup_concepts_by_names(
            [extracted.get("project") or "", *as_str_list(item.personal.get("active_projects"))],
            kind="project",
            limit=8,
        )

        query_terms = unique_texts(
            [
                item.title or "",
                item.summary or "",
                *(extracted.get("topics") or []),
                *(extracted.get("entities") or []),
                *(extracted.get("concepts") or []),
                *_tokens(item.content or "")[:4],
            ]
        )
        query_text = " ".join(query_terms[:6]) or query
        hits = knowledge_search.search(
            query_text,
            limit=max(related_limit + 2, 6),
            mode="hybrid",
            explain=True,
            include_related=True,
        )

        known_url = False
        related_hits: list[dict[str, Any]] = []
        for hit in hits:
            hit_item = hit.get("item")
            if not isinstance(hit_item, IntelItem):
                continue
            if item.url and hit_item.url and hit_item.url == item.url:
                known_url = True
                continue
            related_hits.append(hit)

        matching_concepts = unique_texts([row["name"] for row in concept_hits])[:8]
        related_titles = unique_texts(
            [str(hit["item"].title or "") for hit in related_hits if hit.get("item")]
        )[:related_limit]
        related_ids = unique_texts(
            [str(hit["item"].id or "") for hit in related_hits if hit.get("item")]
        )[:related_limit]
        related_reasons = unique_texts(
            [
                reason
                for hit in related_hits[:related_limit]
                for reason in (hit.get("match_reasons") or [])
                if str(reason or "").strip()
            ]
        )[:6]
        project_name = ""
        if project_hits:
            project_name = str(project_hits[0]["name"] or "")
        elif extracted.get("project"):
            project_name = str(extracted["project"])
        supplements_existing = bool(related_hits or matching_concepts or project_name) and not known_url
        persona_overlap = unique_texts(
            [
                *[name for name in matching_concepts if name in persona_domains],
                *([project_name] if project_name and project_name in persona_projects else []),
            ]
        )[:6]
        follow_up_seed = project_name or (matching_concepts[0] if matching_concepts else "") or query or item.title
        follow_up_payload = research_questions(query=follow_up_seed, limit=question_limit)
        followups = unique_texts(
            [str(row.get("question") or "") for row in (follow_up_payload.get("questions") or [])]
        )[:question_limit]

        linkage = {
            "known_url": known_url,
            "supplements_existing": supplements_existing,
            "related_count": len(related_hits),
            "related_titles": related_titles,
            "related_ids": related_ids,
            "related_reasons": related_reasons,
            "matching_concepts": matching_concepts,
            "project": project_name,
            "persona_overlap": persona_overlap,
            "followups": followups,
        }
        item.personal["knowledge_linkage"] = linkage

        if known_url or related_hits or matching_concepts or project_name:
            linked_count += 1
        if known_url:
            known_url_count += 1
        if supplements_existing:
            supplements_count += 1
        if project_name:
            project_linked_count += 1
            project_counter[project_name] = project_counter.get(project_name, 0) + 1
        if persona_overlap:
            persona_overlap_count += 1
        if followups:
            followup_count += 1
        for concept_name in matching_concepts:
            concept_counter[concept_name] = concept_counter.get(concept_name, 0) + 1

        annotations.append(
            {
                "item_id": item.id,
                "title": item.title,
                "known_url": known_url,
                "supplements_existing": supplements_existing,
                "related_count": len(related_hits),
                "matching_concepts": matching_concepts,
                "project": project_name,
                "persona_overlap": persona_overlap,
                "followups": followups,
            }
        )

    top_concepts = [
        {"name": name, "count": count}
        for name, count in sorted(concept_counter.items(), key=lambda pair: (-pair[1], pair[0]))[:8]
    ]
    top_projects = [
        {"name": name, "count": count}
        for name, count in sorted(project_counter.items(), key=lambda pair: (-pair[1], pair[0]))[:6]
    ]
    return {
        "annotated_items": annotations,
        "summary": {
            "linked_count": linked_count,
            "known_url_count": known_url_count,
            "supplements_count": supplements_count,
            "project_linked_count": project_linked_count,
            "persona_overlap_count": persona_overlap_count,
            "followup_count": followup_count,
            "top_concepts": top_concepts,
            "top_projects": top_projects,
        },
    }


def enrich_item(item_id: str, *, use_ai: bool = False) -> dict[str, Any]:
    del use_ai  # rule-first vertical slice; AI relation candidates can be layered later.
    conn = connect()
    try:
        row = conn.execute("SELECT data_json FROM intel_items WHERE id = ?", (item_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        raise FileNotFoundError(f"item not found: {item_id}")
    item = IntelItem.from_dict(json.loads(row["data_json"]))
    return enrich_item_object(item, persist_item=True)


def enrich_items(items: list[IntelItem], *, persist_items: bool = False) -> dict[str, Any]:
    enriched = 0
    relation_count = 0
    for item in items:
        result = enrich_item_object(item, persist_item=persist_items)
        enriched += 1
        relation_count += len(result.get("relations") or [])
    return {"enriched_items": enriched, "relation_count": relation_count}


def list_concepts(*, query: str = "", kind: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 300))
    sql = "SELECT name, kind, summary, item_count, data_json, updated_at FROM knowledge_concepts WHERE 1=1"
    params: list[Any] = []
    if query:
        sql += " AND name LIKE ?"
        params.append(f"%{query}%")
    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    sql += " ORDER BY item_count DESC, updated_at DESC, name LIMIT ?"
    params.append(safe_limit)
    conn = connect()
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    return [
        {
            "name": row["name"],
            "kind": row["kind"],
            "summary": row["summary"] or "",
            "item_count": int(row["item_count"] or 0),
            "updated_at": row["updated_at"] or "",
        }
        for row in rows
    ]


def get_concept(name: str, *, limit: int = 80) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit), 300))
    conn = connect()
    try:
        row = conn.execute(
            "SELECT name, kind, summary, item_count, data_json, updated_at FROM knowledge_concepts WHERE name = ?",
            (name,),
        ).fetchone()
        item_rows = conn.execute(
            """
            SELECT c.item_id, c.kind, c.confidence, c.status, c.evidence, i.data_json, i.created_at
            FROM knowledge_item_concepts c
            JOIN intel_items i ON i.id = c.item_id
            WHERE c.concept_name = ?
            ORDER BY c.confidence DESC, i.created_at DESC
            LIMIT ?
            """,
            (name, safe_limit),
        ).fetchall()
    finally:
        conn.close()
    items: list[dict[str, Any]] = []
    for item_row in item_rows:
        try:
            item = IntelItem.from_dict(json.loads(item_row["data_json"]))
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        items.append(
            {
                "item": item.to_dict(),
                "confidence": float(item_row["confidence"] or 0.0),
                "status": item_row["status"] or "",
                "evidence": item_row["evidence"] or "",
            }
        )
    concept = {
        "name": name,
        "kind": "",
        "summary": "",
        "item_count": len(items),
        "updated_at": "",
    }
    if row:
        concept.update(
            {
                "name": row["name"],
                "kind": row["kind"],
                "summary": row["summary"] or "",
                "item_count": int(row["item_count"] or 0),
                "updated_at": row["updated_at"] or "",
            }
        )
    return {"concept": concept, "items": items, "count": len(items)}


def _node_id(node_type: str, node_key: str) -> str:
    return f"{node_type}:{node_key}"


def _load_item_nodes(item_ids: set[str]) -> dict[str, dict[str, Any]]:
    if not item_ids:
        return {}
    placeholders = ",".join("?" for _ in item_ids)
    conn = connect()
    try:
        rows = conn.execute(
            f"SELECT id, data_json FROM intel_items WHERE id IN ({placeholders})",
            list(item_ids),
        ).fetchall()
    finally:
        conn.close()
    nodes: dict[str, dict[str, Any]] = {}
    for row in rows:
        try:
            item = IntelItem.from_dict(json.loads(row["data_json"]))
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        nodes[_node_id("item", item.id)] = {
            "id": _node_id("item", item.id),
            "type": "item",
            "item_id": item.id,
            "label": item.title,
            "source": item.source,
            "url": item.url,
            "summary": _clip(item.summary or item.content, 220),
        }
    return nodes


def get_graph(
    *,
    item_id: str | None = None,
    relation: str | None = None,
    min_confidence: float = 0.0,
    limit: int = 200,
) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit), 1000))
    min_conf = max(0.0, min(float(min_confidence or 0.0), 1.0))
    sql = """
        SELECT from_type, from_id, to_type, to_id, relation, confidence, status, evidence, source, data_json
        FROM knowledge_relations
        WHERE confidence >= ?
    """
    params: list[Any] = [min_conf]
    if item_id:
        sql += " AND ((from_type = 'item' AND from_id = ?) OR (to_type = 'item' AND to_id = ?))"
        params.extend([item_id, item_id])
    if relation:
        sql += " AND relation = ?"
        params.append(relation)
    sql += " ORDER BY confidence DESC, created_at DESC LIMIT ?"
    params.append(safe_limit)
    conn = connect()
    try:
        relation_rows = conn.execute(sql, params).fetchall()
        link_rows = conn.execute(
            """
            SELECT from_item_id, to_item_id, relation, confidence, evidence
            FROM knowledge_links
            WHERE confidence >= ?
            ORDER BY confidence DESC
            LIMIT ?
            """,
            (min_conf, safe_limit),
        ).fetchall()
    finally:
        conn.close()

    nodes: dict[str, dict[str, Any]] = {}
    item_ids: set[str] = set()
    edges: list[dict[str, Any]] = []
    for row in relation_rows:
        from_type = str(row["from_type"] or "")
        to_type = str(row["to_type"] or "")
        from_id = str(row["from_id"] or "")
        to_id = str(row["to_id"] or "")
        if from_type == "item":
            item_ids.add(from_id)
        if to_type == "item":
            item_ids.add(to_id)
        from_node = _node_id(from_type, from_id)
        to_node = _node_id(to_type, to_id)
        for node_type, node_key, node_id in ((from_type, from_id, from_node), (to_type, to_id, to_node)):
            if node_type != "item":
                nodes.setdefault(
                    node_id,
                    {
                        "id": node_id,
                        "type": node_type,
                        "label": node_key,
                    },
                )
        edges.append(
            {
                "from": from_node,
                "to": to_node,
                "from_type": from_type,
                "from_id": from_id,
                "to_type": to_type,
                "to_id": to_id,
                "relation": row["relation"],
                "confidence": float(row["confidence"] or 0.0),
                "status": row["status"] or "",
                "evidence": row["evidence"] or "",
                "source": row["source"] or "",
            }
        )
    for row in link_rows:
        if item_id and item_id not in {row["from_item_id"], row["to_item_id"]}:
            continue
        if relation and row["relation"] != relation:
            continue
        item_ids.add(str(row["from_item_id"]))
        item_ids.add(str(row["to_item_id"]))
        edges.append(
            {
                "from": _node_id("item", str(row["from_item_id"])),
                "to": _node_id("item", str(row["to_item_id"])),
                "from_type": "item",
                "from_id": str(row["from_item_id"]),
                "to_type": "item",
                "to_id": str(row["to_item_id"]),
                "relation": row["relation"],
                "confidence": float(row["confidence"] or 0.0),
                "status": "confirmed",
                "evidence": row["evidence"] or "",
                "source": "knowledge_links",
            }
            )
    nodes.update(_load_item_nodes(item_ids))
    return {
        "nodes": list(nodes.values()),
        "edges": edges[:safe_limit],
        "count": {"nodes": len(nodes), "edges": min(len(edges), safe_limit)},
        "filters": {
            "item_id": item_id,
            "relation": relation,
            "min_confidence": min_conf,
            "limit": safe_limit,
        },
    }


def research_questions(
    *,
    item_id: str | None = None,
    topic: str | None = None,
    query: str | None = None,
    limit: int = 8,
) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit), 30))
    questions: list[dict[str, Any]] = []
    if item_id:
        graph = get_graph(item_id=item_id, limit=120)
        for edge in graph["edges"]:
            if edge.get("to_type") == "question":
                questions.append(
                    {
                        "question": edge["to_id"],
                        "source": "item_question",
                        "evidence": edge.get("evidence") or "",
                        "item_id": item_id,
                    }
                )
    for name in unique_texts([topic or "", query or ""]):
        if not name:
            continue
        concept_hits = list_concepts(query=name, limit=safe_limit)
        for concept in concept_hits:
            questions.append(
                {
                    "question": f"围绕「{concept['name']}」还有哪些未覆盖来源或反证？",
                    "source": "concept_gap",
                    "evidence": f"概念已有 {concept['item_count']} 条材料",
                    "concept": concept["name"],
                }
            )
    questions = questions[:safe_limit]
    gaps = [
        {
            "topic": entry.get("concept") or topic or query or entry.get("question", "")[:40],
            "gap": entry["question"],
            "suggested_query": entry["question"].rstrip("？?"),
        }
        for entry in questions
    ]
    return {"questions": questions, "gaps": gaps, "count": len(questions)}


def create_research_from_item(
    *,
    item_id: str,
    tree_id: str | None = None,
    parent_node_id: str | None = None,
) -> dict[str, Any]:
    from osint_toolkit.research.tree import add_node, create_tree, load_tree

    conn = connect()
    try:
        row = conn.execute("SELECT data_json FROM intel_items WHERE id = ?", (item_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        raise FileNotFoundError(f"item not found: {item_id}")
    item = IntelItem.from_dict(json.loads(row["data_json"]))
    if tree_id:
        tree = load_tree(tree_id)
        node = add_node(
            tree_id,
            parent_id=parent_node_id,
            kind="knowledge_item",
            title=item.title[:120] or item_id,
            payload=item.summary or item.content[:500],
            meta={"item_id": item.id, "url": item.url, "source": item.source},
        )
    else:
        tree = create_tree(f"研究: {item.title[:80]}", query=item.title)
        root_id = tree["nodes"][0]["id"]
        node = add_node(
            tree["id"],
            parent_id=root_id,
            kind="knowledge_item",
            title=item.title[:120] or item_id,
            payload=item.summary or item.content[:500],
            meta={"item_id": item.id, "url": item.url, "source": item.source},
        )
        tree = load_tree(tree["id"])
    questions = research_questions(item_id=item_id, limit=6)
    return {"tree": tree, "node": node, "questions": questions.get("questions") or []}
