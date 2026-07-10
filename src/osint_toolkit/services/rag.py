"""Local-first Graph-RAG service for the knowledge core."""

from __future__ import annotations

import json
from typing import Any

from osint_toolkit.ai.client import DeepSeekClient
from osint_toolkit.ai.steering import build_system_prompt
from osint_toolkit.persona.context import maybe_load_persona_context
from osint_toolkit.services import knowledge, vector
from osint_toolkit.storage.sqlite import connect

_CONTEXT_CHARS = 14000
_RELATION_WEIGHTS = {
    "confirmed": 0.12,
    "suggested": 0.05,
    "": 0.04,
}
_CHANNEL_WEIGHTS = {
    "direct": 0.28,
    "concept": 0.22,
    "graph": 0.18,
    "behavior": 0.12,
    "relation_confirmed": 0.2,
    "relation_suggested": 0.12,
    "link_graph": 0.1,
    "semantic": 0.2,
}


def _clip(value: Any, limit: int = 600) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _relation_label(relation: str) -> str:
    return {
        "supports": "支持",
        "contradicts": "冲突",
        "explains": "解释",
        "extends": "延伸",
        "duplicate_of": "近似重复",
        "source_of": "来源依据",
        "mentions_entity": "提到实体",
        "belongs_to_project": "所属项目",
        "same_topic": "同主题",
        "same_entity": "同实体",
    }.get(relation, relation or "关联")


def _hit_to_evidence(hit: dict[str, Any], idx: int) -> dict[str, Any]:
    item = hit["item"]
    reasons = [str(x) for x in (hit.get("match_reasons") or []) if str(x).strip()]
    snippets = [str(x) for x in (hit.get("snippets") or []) if str(x).strip()]
    channel = str(hit.get("match_type") or "direct")
    score = float(hit.get("score") or 0.0) + _CHANNEL_WEIGHTS.get(channel, 0.1)
    concepts = hit.get("concepts") or []
    return {
        "citation": f"k{idx}",
        "item_id": item.id,
        "title": item.title,
        "url": item.url,
        "source": item.source,
        "summary": _clip(item.summary or item.content, 700),
        "snippet": snippets[0] if snippets else _clip(item.summary or item.content, 260),
        "snippets": snippets[:3],
        "source_channel": channel,
        "match_reason": "；".join(reasons[:4]),
        "relation_reason": "",
        "relation": "",
        "relation_status": "",
        "confidence": round(float(hit.get("score") or 0.0), 4),
        "score": round(score, 4),
        "concepts": concepts[:8],
        "project": hit.get("project") or "",
        "needs_verification": False,
    }


def _load_item_payload(item_id: str) -> dict[str, Any] | None:
    conn = connect()
    try:
        row = conn.execute("SELECT data_json FROM intel_items WHERE id = ?", (item_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    try:
        payload = json.loads(row["data_json"] or "{}")
    except (json.JSONDecodeError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def _semantic_to_evidence(row: dict[str, Any]) -> dict[str, Any] | None:
    item_id = str(row.get("item_id") or "")
    if not item_id:
        return None
    payload = _load_item_payload(item_id)
    if payload:
        title = str(payload.get("title") or row.get("title") or "无标题")
        url = str(payload.get("url") or row.get("url") or "")
        source = str(payload.get("source") or row.get("source") or "")
        summary = _clip(payload.get("summary") or payload.get("content") or row.get("text"), 700)
        project = str((payload.get("personal") or {}).get("project") or "")
    else:
        title = str(row.get("title") or "无标题")
        url = str(row.get("url") or "")
        source = str(row.get("source") or "")
        summary = _clip(row.get("text"), 700)
        project = ""
    score = float(row.get("score") or 0.0)
    return {
        "citation": "",
        "item_id": item_id,
        "title": title,
        "url": url,
        "source": source,
        "summary": summary,
        "snippet": _clip(row.get("text") or summary, 260),
        "snippets": [_clip(row.get("text") or summary, 260)],
        "source_channel": "semantic",
        "match_reason": "向量语义召回",
        "relation_reason": "",
        "relation": "",
        "relation_status": "",
        "confidence": round(score, 4),
        "score": round(score + _CHANNEL_WEIGHTS["semantic"], 4),
        "concepts": [],
        "project": project,
        "needs_verification": False,
    }


def _relation_edges(seed_ids: list[str], *, limit: int = 80) -> list[dict[str, Any]]:
    if not seed_ids:
        return []
    placeholders = ",".join("?" for _ in seed_ids)
    conn = connect()
    try:
        relation_rows = conn.execute(
            f"""
            SELECT from_id, to_id, relation, confidence, status, evidence, source
            FROM knowledge_relations
            WHERE from_type = 'item'
              AND to_type = 'item'
              AND (from_id IN ({placeholders}) OR to_id IN ({placeholders}))
              AND COALESCE(status, '') != 'rejected'
            ORDER BY CASE status WHEN 'confirmed' THEN 0 ELSE 1 END, confidence DESC, created_at DESC
            LIMIT ?
            """,
            [*seed_ids, *seed_ids, max(1, min(int(limit), 300))],
        ).fetchall()
        link_rows = conn.execute(
            f"""
            SELECT from_item_id AS from_id, to_item_id AS to_id, relation, confidence,
                   'confirmed' AS status, evidence, 'knowledge_links' AS source
            FROM knowledge_links
            WHERE from_item_id IN ({placeholders}) OR to_item_id IN ({placeholders})
            ORDER BY confidence DESC
            LIMIT ?
            """,
            [*seed_ids, *seed_ids, max(1, min(int(limit), 300))],
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in [*relation_rows, *link_rows]]


def _expand_evidence(seed_evidence: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    seed_ids = [str(ev.get("item_id") or "") for ev in seed_evidence if ev.get("item_id")]
    seed_scores = {str(ev["item_id"]): float(ev.get("score") or 0.0) for ev in seed_evidence if ev.get("item_id")}
    expanded: dict[str, dict[str, Any]] = {}
    for edge in _relation_edges(seed_ids, limit=max(20, limit * 4)):
        from_id = str(edge.get("from_id") or "")
        to_id = str(edge.get("to_id") or "")
        seed_id = from_id if from_id in seed_scores else to_id if to_id in seed_scores else ""
        related_id = to_id if seed_id == from_id else from_id
        if not seed_id or not related_id or related_id == seed_id:
            continue
        payload = _load_item_payload(related_id)
        if not payload:
            continue
        relation = str(edge.get("relation") or "")
        status = str(edge.get("status") or "")
        confidence = float(edge.get("confidence") or 0.0)
        channel = "link_graph" if edge.get("source") == "knowledge_links" else f"relation_{status or 'suggested'}"
        relation_reason = f"{_relation_label(relation)}关系"
        if edge.get("evidence"):
            relation_reason += f": {edge['evidence']}"
        score = seed_scores[seed_id] * 0.42 + confidence * 0.35 + _RELATION_WEIGHTS.get(status, 0.04)
        ev = {
            "citation": "",
            "item_id": related_id,
            "title": str(payload.get("title") or "无标题"),
            "url": str(payload.get("url") or ""),
            "source": str(payload.get("source") or ""),
            "summary": _clip(payload.get("summary") or payload.get("content"), 700),
            "snippet": _clip(payload.get("summary") or payload.get("content"), 260),
            "snippets": [],
            "source_channel": channel,
            "match_reason": "",
            "relation_reason": relation_reason,
            "relation": relation,
            "relation_status": status,
            "confidence": round(confidence, 4),
            "score": round(score, 4),
            "concepts": [],
            "project": str((payload.get("personal") or {}).get("project") or ""),
            "needs_verification": relation == "contradicts",
        }
        prev = expanded.get(related_id)
        if prev is None or ev["score"] > prev["score"]:
            expanded[related_id] = ev
    return sorted(expanded.values(), key=lambda row: float(row.get("score") or 0.0), reverse=True)[:limit]


def retrieve(
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
    limit: int = 10,
    expand_graph: bool = True,
    include_semantic: bool = True,
) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit), 50))
    hits = knowledge.search(
        query,
        mode=mode,
        source=source,
        topic=topic,
        tag=tag,
        entity=entity,
        run_id=run_id,
        capture_reason=capture_reason,
        conflict_status=conflict_status,
        limit=safe_limit,
        explain=True,
        include_related=False,
    )
    direct = [_hit_to_evidence(hit, idx) for idx, hit in enumerate(hits, start=1)]
    semantic: list[dict[str, Any]] = []
    if include_semantic:
        try:
            semantic = [
                ev
                for ev in (_semantic_to_evidence(row) for row in vector.search(query, limit=safe_limit))
                if ev is not None
            ]
        except Exception:  # noqa: BLE001
            semantic = []
    expanded = _expand_evidence(direct[:8], limit=safe_limit) if expand_graph else []
    by_id: dict[str, dict[str, Any]] = {}
    channel_rank = {
        "relation_confirmed": 5,
        "relation_suggested": 4,
        "link_graph": 3,
        "semantic": 3,
        "graph": 2,
        "concept": 2,
        "direct": 2,
        "behavior": 1,
    }
    for ev in [*direct, *semantic, *expanded]:
        item_id = str(ev.get("item_id") or "")
        if not item_id:
            continue
        prev = by_id.get(item_id)
        ev_rank = channel_rank.get(str(ev.get("source_channel") or ""), 0)
        prev_rank = channel_rank.get(str((prev or {}).get("source_channel") or ""), 0)
        if (
            prev is None
            or ev_rank > prev_rank
            or (
                ev_rank == prev_rank
                and float(ev.get("score") or 0.0) > float(prev.get("score") or 0.0)
            )
        ):
            by_id[item_id] = ev
    evidence = sorted(by_id.values(), key=lambda row: float(row.get("score") or 0.0), reverse=True)[:safe_limit]
    for idx, ev in enumerate(evidence, start=1):
        ev["citation"] = f"k{idx}"
    suggestions = knowledge.search_suggestions(query, limit=8) if not evidence else {}
    return {
        "query": query,
        "evidence": evidence,
        "count": len(evidence),
        "channels": sorted({str(ev.get("source_channel") or "") for ev in evidence if ev.get("source_channel")}),
        "suggestions": suggestions,
    }


def retrieve_context(query: str, *, limit: int = 8, max_chars: int = _CONTEXT_CHARS, **filters: Any) -> dict[str, Any]:
    payload = retrieve(query, limit=limit, **filters)
    persona_ctx = maybe_load_persona_context()
    try:
        concepts = knowledge.list_concepts(query=query, limit=8)
    except Exception:  # noqa: BLE001
        concepts = []
    try:
        projects = knowledge.list_concepts(query=query, kind="project", limit=5)
    except Exception:  # noqa: BLE001
        projects = []
    try:
        gaps = knowledge.research_questions(query=query, limit=5)
    except Exception:  # noqa: BLE001
        gaps = {"questions": [], "gaps": [], "count": 0}
    context = {
        "query": query,
        "evidence": payload["evidence"],
        "knowledge_concepts": concepts,
        "knowledge_projects": projects,
        "knowledge_gaps": gaps,
        "persona": {
            "brief": _clip(persona_ctx.brief if persona_ctx else "", 1600),
            "structured": persona_ctx.structured if persona_ctx else {},
            "stale": bool(persona_ctx.stale) if persona_ctx else False,
        },
    }
    context_blob = json.dumps(context, ensure_ascii=False, default=str)
    if len(context_blob) > max_chars:
        context["truncated"] = True
        context["evidence"] = context["evidence"][: max(3, min(len(context["evidence"]), 6))]
    return context


def _fallback_answer(question: str, context: dict[str, Any]) -> str:
    evidence = context.get("evidence") or []
    if not evidence:
        return "知识库里暂时没有足够证据回答这个问题。可以先换关键词检索，或把它作为新一轮搜罗问题。"
    lines = [
        "当前未调用 AI，下面按本地 RAG 证据整理。",
        "",
        f"问题: {question}",
        "",
        "依据:",
    ]
    for ev in evidence[:6]:
        citation = ev.get("citation") or ""
        title = ev.get("title") or "无标题"
        reason = ev.get("match_reason") or ev.get("relation_reason") or ev.get("snippet") or "命中知识库"
        mark = "（存在冲突，需核查）" if ev.get("needs_verification") else ""
        lines.append(f"- [{citation}] {title}{mark}: {reason}")
    return "\n".join(lines).strip()


def _messages(question: str, context: dict[str, Any], history: list[dict[str, str]] | None) -> list[dict[str, str]]:
    persona = context.get("persona") or {}
    system = build_system_prompt(task="知识库 RAG 问答", persona_brief=str(persona.get("brief") or ""))
    system += (
        "\n你只能基于提供的 RAG evidence 作答。"
        "每个关键结论必须引用 [k1] 这样的 citation。"
        "如果证据不足，明确说不足，不得编造。"
        "遇到 contradicts/冲突证据时必须标注需核查。"
    )
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    for turn in history or []:
        q = str(turn.get("question") or "").strip()
        a = str(turn.get("answer") or "").strip()
        if q:
            messages.append({"role": "user", "content": q})
        if a:
            messages.append({"role": "assistant", "content": a})
    context_blob = json.dumps(context, ensure_ascii=False, default=str)
    if len(context_blob) > _CONTEXT_CHARS:
        context_blob = context_blob[:_CONTEXT_CHARS] + "...(已截断)"
    messages.append({"role": "user", "content": f"RAG 上下文:\n{context_blob}\n\n问题: {question}"})
    return messages


def ask(
    question: str,
    *,
    mode: str = "hybrid",
    source: str | None = None,
    topic: str | None = None,
    tag: str | None = None,
    entity: str | None = None,
    run_id: str | None = None,
    capture_reason: str | None = None,
    conflict_status: str | None = None,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    context = retrieve_context(
        question,
        mode=mode,
        source=source,
        topic=topic,
        tag=tag,
        entity=entity,
        run_id=run_id,
        capture_reason=capture_reason,
        conflict_status=conflict_status,
        limit=10,
    )
    gaps = context.get("knowledge_gaps") or {}
    if not context.get("evidence"):
        suggestions = knowledge.search_suggestions(question, limit=8)
        return {
            "ok": True,
            "question": question,
            "answer": _fallback_answer(question, context),
            "hits": [],
            "evidence": [],
            "context": context,
            "ai_used": False,
            "fallback": "no_evidence",
            "follow_up_questions": suggestions.get("follow_up_questions") or [],
            "suggestions": suggestions,
        }
    try:
        client = DeepSeekClient()
        answer = client.chat(messages=_messages(question, context, history))
        if not answer or len(answer.strip()) < 2:
            raise RuntimeError("AI 返回空内容")
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "api" in msg.lower() and "key" in msg.lower():
            msg = "未配置 DeepSeek API Key，已回退为本地 RAG 证据整理"
        return {
            "ok": True,
            "question": question,
            "answer": _fallback_answer(question, context),
            "hits": context["evidence"],
            "evidence": context["evidence"],
            "context": context,
            "ai_used": False,
            "fallback": "local_rag",
            "follow_up_questions": gaps.get("questions") or [],
            "warning": msg,
        }
    return {
        "ok": True,
        "question": question,
        "answer": answer,
        "hits": context["evidence"],
        "evidence": context["evidence"],
        "context": context,
        "ai_used": True,
        "fallback": "",
        "follow_up_questions": gaps.get("questions") or [],
    }
