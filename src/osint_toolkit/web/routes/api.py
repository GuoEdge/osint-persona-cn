"""REST API 路由 / REST API routes."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response, StreamingResponse

from osint_toolkit.research.tree import (
    add_node,
    attach_search_node,
    create_tree,
    delete_node,
    delete_tree,
    find_search_node_id_for_run,
    list_trees,
    load_tree,
    patch_node,
    rename_tree,
    tree_to_markmap,
)
from osint_toolkit.services import (
    ai_config,
    auth,
    browser_sync,
    dependencies,
    digest,
    events,
    extension,
    feedback,
    health,
    ingest,
    ingest_capabilities,
    knowledge,
    persona,
    research_ai,
    runs,
    save,
    secrets,
    setup,
    tools,
)
from osint_toolkit.services import search as search_service
from osint_toolkit.services import watch as watch_service
from osint_toolkit.services.ask import ask_question
from osint_toolkit.services.run_session import read_manifest, read_progress_disk
from osint_toolkit.services.search_fork import build_fork_search_params
from osint_toolkit.utils.config import load_sync_config
from osint_toolkit.utils.safe_path import (
    PathSecurityError,
    assert_domain,
    assert_prompt_name,
    assert_safe_id,
    coerce_run_dir_id,
)
from osint_toolkit.web.schemas import (
    AskRequest,
    BrowserSyncRequest,
    DirectivesUpdate,
    ExtensionEventsRequest,
    ExtensionPingRequest,
    FeedbackRequest,
    ImportCookiesRequest,
    IngestAicuJsonRequest,
    IngestBrowserRequest,
    KnowledgeBatchDeleteRequest,
    PersonaRollbackRequest,
    PromptUpdate,
    ResearchInsightRequest,
    ResearchNodeCreate,
    ResearchNodePatch,
    ResearchSuggestRequest,
    ResearchTreeCreate,
    ResearchTreeRename,
    RunsBatchDeleteRequest,
    RunsCleanupRequest,
    SaveRequest,
    SaveRunItemsRequest,
    SearchExpandRequest,
    SearchRequest,
    SecretSaveRequest,
    SimOverrideRequest,
    SyncCookiesRequest,
    TunablePatchRequest,
)
from osint_toolkit.web.tasks import (
    SearchQueueFullError,
    cancel_job,
    drain_search_queue,
    get_job,
    get_job_result,
    job_public_view,
    list_active_jobs,
    list_active_searches,
    list_search_tasks,
    start_browser_sync_job,
    start_full_sync_job,
    start_playwright_install_job,
    start_search_job,
)

router = APIRouter(prefix="/api")

_STEP_FILE_RE = re.compile(r"^\d+_.+\.json$")

_MANIFEST_CACHE: dict[str, tuple[int, dict[str, Any] | None]] = {}


def read_manifest_cached(run_id: str) -> dict[str, Any] | None:
    from osint_toolkit.services.run_session import run_dir

    path = run_dir(run_id) / "manifest.json"
    try:
        mtime_ns = path.stat().st_mtime_ns
    except OSError:
        _MANIFEST_CACHE.pop(run_id, None)
        return None
    cached = _MANIFEST_CACHE.get(run_id)
    if cached and cached[0] == mtime_ns:
        return cached[1]
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        parsed = None
    _MANIFEST_CACHE[run_id] = (mtime_ns, parsed)
    return parsed


def _scan_run_dir(run_id: str, seen: frozenset[str]) -> dict[str, Any]:
    """Sync helper for SSE event_stream: read manifest, progress, and new step files.

    Receives an immutable *frozenset* copy of the caller's ``seen`` set so that
    all ``seen`` mutations happen on the async side (main thread), never inside
    the worker thread.  Returns ``new_file_names`` (ALL matched files, including
    ones that fail JSON parsing) so the caller can update ``seen`` exactly once
    per file, preserving the original skip-on-parse-error behaviour.
    """
    from osint_toolkit.pipeline.progress import get_progress
    from osint_toolkit.services.run_session import run_dir as get_run_dir

    manifest = read_manifest_cached(run_id)
    progress = get_progress(run_id)
    run_dir_path = get_run_dir(run_id)
    new_steps: list[dict[str, Any]] = []
    new_file_names: list[str] = []
    if run_dir_path.exists():
        new_files = sorted(
            p
            for p in run_dir_path.glob("*_*.json")
            if p.name not in seen and _STEP_FILE_RE.match(p.name)
        )
        for path in new_files:
            new_file_names.append(path.name)
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            new_steps.append({"file": path.name, "data": data})
    return {
        "manifest": manifest,
        "progress": progress,
        "new_steps": new_steps,
        "new_file_names": new_file_names,
    }


@router.get("/health")
async def api_health() -> dict[str, str]:
    """轻量探活；同时由中间件写入 Web Token Cookie，供 EventSource 等无法带头部的请求鉴权。"""
    return {"ok": "true"}


def _validated_run_id(run_id: str) -> str:
    try:
        return coerce_run_dir_id(run_id)
    except PathSecurityError as exc:
        raise HTTPException(400, detail=str(exc)) from exc


def _validated_tree_id(tree_id: str) -> str:
    try:
        return assert_safe_id(tree_id, label="tree_id")
    except PathSecurityError as exc:
        raise HTTPException(400, detail=str(exc)) from exc


def _validated_prompt_name(name: str) -> str:
    try:
        return assert_prompt_name(name)
    except PathSecurityError as exc:
        raise HTTPException(400, detail=str(exc)) from exc


def _serialize_search_result(result: dict[str, Any]) -> dict[str, Any]:
    items = result.get("items") or []
    qa = result.get("query_analysis") or {}
    return {
        "run_id": result["run_id"],
        "items": [i.to_dict() if hasattr(i, "to_dict") else i for i in items],
        "report": result.get("report", ""),
        "report_path": result.get("report_path"),
        "simulations": result.get("simulations", []),
        "source_errors": result.get("source_errors") or [],
        "source_warnings": result.get("source_warnings") or [],
        "citation_map": result.get("citation_map") or {},
        "citation_urls": result.get("citation_urls") or {},
        "intel_stats": result.get("intel_stats") or {},
        "query_analysis": qa,
        "source_plan": qa.get("source_plan") or {},
        "source_routing": qa.get("source_routing") or {},
        "collect_sources": result.get("collect_sources") or qa.get("active_sources") or [],
        "queries_used": result.get("queries_used") or qa.get("queries_used") or [],
        "discover_meta": result.get("discover_meta") or {},
        "no_ai": bool(result.get("no_ai")),
    }


@router.get("/search/source-catalog")
async def api_search_source_catalog() -> dict[str, Any]:
    from osint_toolkit.collectors.source_catalog import get_catalog_grouped, get_source_entries

    return {
        "groups": await asyncio.to_thread(get_catalog_grouped),
        "entries": await asyncio.to_thread(get_source_entries),
    }


@router.get("/sources/auth-check")
async def api_sources_auth_check(sources: str = "") -> dict[str, Any]:
    from osint_toolkit.collectors.registry import COLLECTORS
    from osint_toolkit.services.source_preflight import check_sources_auth

    ids = [s.strip() for s in sources.split(",") if s.strip() and s.strip() in COLLECTORS]
    return await asyncio.to_thread(check_sources_auth, ids)


@router.post("/search/expand")
async def api_search_expand(body: SearchExpandRequest) -> dict[str, Any]:
    return await search_service.preview_query_expansion(
        body.query,
        body.sources,
        no_ai=body.no_ai,
        include_slurs=body.include_slurs,
        profile=body.profile,
        source_overrides=body.source_overrides,
    )


@router.post("/search")
async def api_search(body: SearchRequest) -> dict[str, Any]:
    if not body.mine_comments:
        comment_mine_top = 0
    elif body.comment_mine_top is None or body.comment_mine_top <= 0:
        comment_mine_top = 12
    else:
        comment_mine_top = body.comment_mine_top

    tree_id = body.tree_id
    parent_node_id = body.parent_node_id
    if body.create_tree and not tree_id:
        created = await asyncio.to_thread(create_tree, body.query, query=body.query)
        tree_id = created["id"]
        parent_node_id = created["nodes"][0]["id"]

    search_kwargs: dict[str, Any] = {
        "query": body.query,
        "sources": body.sources,
        "limit": body.limit,
        "digest": body.digest,
        "trace": body.trace,
        "profile": body.profile,
        "ai_instruct": body.ai_instruct,
        "no_ai": body.no_ai,
        "no_simulate": body.no_simulate,
        "disabled_ai_steps": body.disabled_ai_steps,
        "deep_top": body.deep_top,
        "comment_mine_top": comment_mine_top,
        "include_slurs": body.include_slurs,
        "source_overrides": body.source_overrides,
        "serp_fallback_accepted": body.serp_fallback_accepted,
        "comment_mine_sources": body.comment_mine_sources,
        "tree_id": tree_id,
        "parent_node_id": parent_node_id,
    }
    if body.fork_from_run_id:
        search_kwargs = await asyncio.to_thread(
            build_fork_search_params,
            body.fork_from_run_id,
            {**search_kwargs, "query": body.query or search_kwargs.get("query", "")},
        )

    tree_id = search_kwargs.get("tree_id") or tree_id
    parent_node_id = search_kwargs.get("parent_node_id") or parent_node_id
    if body.fork_from_run_id and tree_id:
        fork_parent = await asyncio.to_thread(find_search_node_id_for_run, tree_id, body.fork_from_run_id)
        if fork_parent:
            parent_node_id = fork_parent
    if tree_id:
        search_kwargs["tree_id"] = tree_id
        search_kwargs["parent_node_id"] = parent_node_id

    try:
        started = start_search_job(**search_kwargs)
    except SearchQueueFullError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    run_id = started["run_id"]
    if tree_id:
        await asyncio.to_thread(
            attach_search_node,
            tree_id,
            parent_node_id=parent_node_id,
            run_id=run_id,
            query=str(search_kwargs.get("query") or body.query),
            meta={"fork_from_run_id": body.fork_from_run_id},
        )
    payload: dict[str, Any] = {
        "run_id": run_id,
        "status": started.get("status", "running"),
        "tree_id": tree_id,
    }
    if started.get("queue_position") is not None:
        payload["queue_position"] = started["queue_position"]
    return payload


@router.get("/search/active")
async def api_search_active() -> dict[str, Any]:
    return {"searches": list_active_searches()}


@router.get("/search/tasks")
async def api_search_tasks(limit: int = 30) -> dict[str, Any]:
    safe_limit = max(1, min(100, int(limit)))
    return {"tasks": list_search_tasks(limit=safe_limit)}


@router.get("/jobs/active")
async def api_jobs_active() -> dict[str, Any]:
    return {"jobs": list_active_jobs()}


@router.post("/search/{run_id}/save-items")
async def api_search_save_items(run_id: str, body: SaveRunItemsRequest) -> dict[str, Any]:
    run_id = _validated_run_id(run_id)
    try:
        return await asyncio.to_thread(
            save.save_run_items,
            run_id,
            item_ids=body.item_ids,
            min_relevance=body.min_relevance,
            tags=body.tags,
        )
    except FileNotFoundError as exc:
        raise HTTPException(404, detail=str(exc)) from exc


@router.get("/runs/{run_id}/diff")
async def api_run_diff(run_id: str, since_run: str) -> dict[str, Any]:
    run_id = _validated_run_id(run_id)
    since_run = _validated_run_id(since_run)
    try:
        return await asyncio.to_thread(runs.diff_run_urls, run_id, since_run)
    except FileNotFoundError as exc:
        raise HTTPException(404, detail=str(exc)) from exc


@router.get("/search/{run_id}/progress")
async def api_search_progress(run_id: str) -> dict[str, Any]:
    from osint_toolkit.pipeline.progress import get_progress

    run_id = _validated_run_id(run_id)
    progress = get_progress(run_id)
    if not progress:
        progress = await asyncio.to_thread(read_progress_disk, run_id)
    if not progress:
        raise HTTPException(404, detail="progress not found")
    return {"run_id": run_id, "progress": progress}


@router.get("/search/{run_id}")
async def api_search_result(run_id: str) -> dict[str, Any]:
    run_id = _validated_run_id(run_id)
    job = get_job(run_id)
    if job:
        if job["status"] == "queued":
            payload = {
                "run_id": run_id,
                "status": "queued",
                "query": job.get("query", ""),
            }
            if job.get("queue_position") is not None:
                payload["queue_position"] = job["queue_position"]
            return payload
        if job["status"] == "running":
            payload: dict[str, Any] = {"run_id": run_id, "status": "running"}
            progress = job_public_view(run_id, job).get("progress")
            if progress:
                payload["progress"] = progress
            return payload
        if job["status"] == "cancelled":
            return {"run_id": run_id, "status": "cancelled", "error": job.get("error") or "已取消"}
        if job["status"] == "error":
            raise HTTPException(500, detail=job["error"])
        result = job.get("result") or await asyncio.to_thread(get_job_result, run_id)
        if not result:
            raise HTTPException(404, detail="run not found")
        return {"run_id": run_id, "status": "done", **_serialize_search_result(result)}
    disk = await asyncio.to_thread(get_job_result, run_id)
    if disk:
        manifest = disk.get("manifest") or {}
        status = manifest.get("status") or "done"
        payload = _serialize_search_result(disk)
        payload["manifest"] = manifest
        if status in ("interrupted", "cancelled", "error"):
            return {
                "run_id": run_id,
                "status": status,
                "error": manifest.get("error"),
                **payload,
            }
        return {"run_id": run_id, "status": "done", **payload}
    manifest_only = await asyncio.to_thread(read_manifest, run_id)
    if manifest_only:
        status = manifest_only.get("status") or "unknown"
        if status == "running":
            payload = {"run_id": run_id, "status": "running"}
            progress = await asyncio.to_thread(read_progress_disk, run_id)
            if progress:
                payload["progress"] = progress
            return payload
        return {
            "run_id": run_id,
            "status": status,
            "error": manifest_only.get("error"),
        }
    raise HTTPException(404, detail="run not found")


@router.post("/search/{run_id}/cancel")
async def api_search_cancel(run_id: str) -> dict[str, Any]:
    run_id = _validated_run_id(run_id)
    if not await asyncio.to_thread(cancel_job, run_id):
        job = get_job(run_id)
        if not job:
            raise HTTPException(404, detail="run not found")
        if job.get("status") != "running":
            return {"run_id": run_id, "status": job.get("status"), "cancelled": False}
        raise HTTPException(409, detail="无法取消该任务")
    return {"run_id": run_id, "status": "cancelling", "cancelled": True}


@router.get("/search/{run_id}/events")
async def api_search_events(run_id: str, request: Request) -> StreamingResponse:
    run_id = _validated_run_id(run_id)

    async def event_stream():
        from osint_toolkit.utils.config import get_search_config

        search_cfg = await asyncio.to_thread(get_search_config)
        collect_timeout = float(search_cfg.get("collect_timeout_sec", 900))
        sse_max_lifetime = float(search_cfg.get("sse_max_lifetime_sec", 3600))
        sse_ticks = max(1200, int(sse_max_lifetime / 0.5), int(collect_timeout * 4 / 0.5))

        seen: set[str] = set()
        last_progress: str | None = None
        tick = 0
        while tick < sse_ticks:
            tick += 1
            if await request.is_disconnected():
                break
            job = get_job(run_id)
            scan = await asyncio.to_thread(_scan_run_dir, run_id, frozenset(seen))
            manifest = scan["manifest"] if not job else None
            terminal_status: str | None = None
            if job and job.get("status") in ("done", "cancelled", "error"):
                terminal_status = str(job["status"])
            elif manifest and manifest.get("status") in (
                "done",
                "cancelled",
                "error",
                "interrupted",
            ):
                terminal_status = str(manifest["status"])
            progress = scan["progress"]
            if progress:
                progress_key = json.dumps(progress, ensure_ascii=False, sort_keys=True)
                if progress_key != last_progress:
                    last_progress = progress_key
                    yield f"data: {json.dumps({'type': 'progress', 'progress': progress}, ensure_ascii=False)}\n\n"
            for name in scan["new_file_names"]:
                seen.add(name)
            for step in scan["new_steps"]:
                data = step["data"]
                payload = json.dumps({"type": "step", "file": step["file"], "step": data}, ensure_ascii=False)
                yield f"data: {payload}\n\n"
                step_data = data.get("data") if isinstance(data, dict) else None
                if isinstance(step_data, dict) and step_data.get("source_errors"):
                    err_payload = json.dumps(
                        {"type": "source_error", "errors": step_data["source_errors"]},
                        ensure_ascii=False,
                    )
                    yield f"data: {err_payload}\n\n"
                if isinstance(step_data, dict) and step_data.get("source_warnings"):
                    warn_payload = json.dumps(
                        {"type": "source_warning", "warnings": step_data["source_warnings"]},
                        ensure_ascii=False,
                    )
                    yield f"data: {warn_payload}\n\n"
                plan_payload = None
                if isinstance(step_data, dict):
                    if step_data.get("source_plan") or step_data.get("source_routing"):
                        plan_payload = {
                            "source_plan": step_data.get("source_plan") or {},
                            "source_routing": step_data.get("source_routing") or {},
                            "collect_sources": step_data.get("active_sources") or [],
                        }
                elif isinstance(data, dict) and data.get("step") == "ai_source_plan":
                    inner = data.get("data") if isinstance(data.get("data"), dict) else data
                    if isinstance(inner, dict) and (
                        inner.get("source_plan") or inner.get("source_routing")
                    ):
                        plan_payload = {
                            "source_plan": inner.get("source_plan") or {},
                            "source_routing": inner.get("source_routing") or {},
                            "collect_sources": inner.get("active_sources") or [],
                        }
                if plan_payload:
                    yield f"data: {json.dumps({'type': 'source_plan', **plan_payload}, ensure_ascii=False)}\n\n"
            if job and job["status"] == "done":
                yield f"data: {json.dumps({'type': 'done', 'run_id': run_id}, ensure_ascii=False)}\n\n"
                break
            if terminal_status == "done":
                yield f"data: {json.dumps({'type': 'done', 'run_id': run_id}, ensure_ascii=False)}\n\n"
                break
            if job and job["status"] == "cancelled":
                yield f"data: {json.dumps({'type': 'cancelled', 'error': job.get('error') or '已取消'}, ensure_ascii=False)}\n\n"
                break
            if terminal_status == "cancelled":
                err = (manifest or {}).get("error") or "已取消"
                yield f"data: {json.dumps({'type': 'cancelled', 'error': err}, ensure_ascii=False)}\n\n"
                break
            if job and job["status"] == "error":
                yield f"data: {json.dumps({'type': 'error', 'error': job['error']}, ensure_ascii=False)}\n\n"
                break
            if terminal_status in ("error", "interrupted"):
                err = (manifest or {}).get("error") or terminal_status
                yield f"data: {json.dumps({'type': 'error', 'error': err}, ensure_ascii=False)}\n\n"
                break
            yield f"data: {json.dumps({'type': 'ping'})}\n\n"
            await asyncio.sleep(0.5)
        else:
            yield f"data: {json.dumps({'type': 'timeout'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/save")
async def api_save(body: SaveRequest) -> dict[str, Any]:
    try:
        result = await save.save_url(body.url, with_comments=body.with_comments, no_ai=body.no_ai)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": result["item"].to_dict(), "card_path": result["card_path"]}


@router.get("/knowledge/recall")
async def api_recall(q: str, limit: int = 20) -> dict[str, Any]:
    limit = max(1, min(limit, 200))
    items = await asyncio.to_thread(knowledge.recall, q, limit=limit)
    return {"items": [i.to_dict() for i in items], "count": len(items)}


@router.get("/knowledge/items")
async def api_knowledge_items(
    q: str = "",
    source: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    items = await asyncio.to_thread(
        knowledge.list_items, query=q, source=source, limit=limit, offset=offset
    )
    return {
        "items": [i.to_dict() for i in items],
        "count": len(items),
        "total": await asyncio.to_thread(knowledge.count_items, source=source),
    }


@router.delete("/knowledge/items/{item_id}")
async def api_knowledge_delete_item(item_id: str) -> dict[str, Any]:
    deleted = await asyncio.to_thread(knowledge.delete_item, item_id)
    if not deleted:
        raise HTTPException(404, detail="item not found")
    return {"item_id": item_id, "deleted": True}


@router.post("/knowledge/items/delete")
async def api_knowledge_batch_delete(body: KnowledgeBatchDeleteRequest) -> dict[str, Any]:
    deleted = await asyncio.to_thread(knowledge.delete_items, body.item_ids)
    return {"deleted": deleted, "requested": len(body.item_ids)}


@router.get("/knowledge/topics")
async def api_knowledge_topics(limit: int = 50) -> dict[str, Any]:
    limit = max(1, min(limit, 200))
    topics = await asyncio.to_thread(knowledge.list_topics, limit=limit)
    return {"topics": topics, "count": len(topics)}


@router.post("/ask")
async def api_ask(body: AskRequest) -> dict[str, Any]:
    history = [
        {"question": str(h.get("question") or ""), "answer": str(h.get("answer") or "")}
        for h in (body.history or [])
        if isinstance(h, dict) and (h.get("question") or h.get("answer"))
    ][-8:]
    result = await asyncio.to_thread(
        ask_question,
        body.question,
        run_id=body.run_id,
        history=history or None,
    )
    if result.get("ok") is False:
        return result
    if body.tree_id and result.get("answer"):
        parent = body.parent_node_id
        if not parent and body.run_id:
            tree_data = await asyncio.to_thread(load_tree, body.tree_id)
            for node in tree_data.get("nodes") or []:
                if node.get("run_id") == body.run_id:
                    parent = node.get("id")
                    break
        try:
            await asyncio.to_thread(
                add_node,
                body.tree_id,
                parent_id=parent,
                kind="ask",
                title=body.question[:80],
                payload=f"Q: {body.question}\n\nA: {result.get('answer', '')}",
                meta={"run_id": body.run_id},
            )
        except ValueError:
            pass
    return result


@router.post("/feedback")
async def api_feedback(body: FeedbackRequest) -> dict[str, Any]:
    return await asyncio.to_thread(
        feedback.submit_feedback,
        target_id=body.target_id,
        rating=body.rating,
        reason=body.reason,
        run_id=body.run_id,
        step=body.step,
        target_type=body.target_type,
        sim_verdict=body.sim_verdict,
    )


@router.get("/feedback/recent")
async def api_feedback_recent(target_ids: str = "") -> dict[str, Any]:
    ids = [part.strip() for part in target_ids.split(",") if part.strip()]
    return {"feedback": await asyncio.to_thread(feedback.get_feedback_map, ids or None)}


@router.post("/runs/{run_id}/sim-override")
async def api_sim_override(run_id: str, body: SimOverrideRequest) -> dict[str, Any]:
    rid = _validated_run_id(run_id)
    return await asyncio.to_thread(
        feedback.override_simulation,
        run_id=rid,
        item_id=body.item_id,
        interest=body.interest,
        confidence=body.confidence,
        verdict=body.verdict,
        reason=body.reason,
    )


@router.get("/digest/daily")
async def api_digest_daily(ai: bool = False, no_ai: bool = False, hot_list: bool = True) -> dict[str, str]:
    content = await asyncio.to_thread(
        digest.get_daily_digest, use_ai=ai, no_ai=no_ai, include_hot_list=hot_list
    )
    return {"content": content}


@router.get("/digest/history")
async def api_digest_history(limit: int = 30) -> dict[str, Any]:
    return {"digests": await asyncio.to_thread(digest.list_daily_digests, limit=limit)}


@router.get("/digest/history/{date}")
async def api_digest_history_one(date: str) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(digest.load_daily_digest, date)
    except FileNotFoundError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc


@router.get("/digest/reports")
async def api_digest_reports(limit: int = 50) -> dict[str, Any]:
    return {"reports": await asyncio.to_thread(digest.list_reports, limit=limit)}


@router.post("/ingest/browser")
async def api_ingest_browser(body: IngestBrowserRequest) -> dict[str, Any]:
    return await asyncio.to_thread(ingest.ingest_browser, since_days=body.since_days)


@router.post("/ingest/bilibili")
async def api_ingest_bilibili() -> dict[str, Any]:
    return await ingest.ingest_bilibili(include_favorites=True, include_likes=True)


@router.get("/ingest/bilibili-mid")
async def api_bilibili_mid() -> dict[str, Any]:
    return await ingest.bilibili_mid()


@router.get("/ingest/aicu-status")
async def api_aicu_status(probe: bool = False) -> dict[str, Any]:
    return await ingest.aicu_status_detail(probe=probe)


@router.post("/ingest/aicu-comments")
async def api_ingest_aicu_comments() -> dict[str, Any]:
    return await ingest.ingest_aicu()


@router.post("/ingest/aicu-json")
async def api_ingest_aicu_json(body: IngestAicuJsonRequest) -> dict[str, Any]:
    payload: Any = body.payload
    if body.pages:
        payload = body.pages
    elif body.replies:
        payload = body.replies
    return await ingest.ingest_aicu_json(payload)


@router.get("/ingest/capabilities")
async def api_ingest_capabilities() -> dict[str, Any]:
    return ingest_capabilities.get_capabilities()


@router.get("/setup/status")
async def api_setup_status() -> dict[str, Any]:
    return await asyncio.to_thread(setup.get_setup_status)


@router.get("/setup/operations")
async def api_setup_operations() -> dict[str, Any]:
    from osint_toolkit.services import ops

    return ops.get_operations_runbook()


@router.get("/setup/sync-config")
async def api_setup_sync_config() -> dict[str, Any]:
    return await asyncio.to_thread(load_sync_config)


@router.post("/setup/dismiss")
async def api_setup_dismiss() -> dict[str, Any]:
    await asyncio.to_thread(setup.dismiss_setup)
    return {"ok": True}


@router.get("/setup/dependencies")
async def api_setup_dependencies() -> dict[str, Any]:
    return await asyncio.to_thread(dependencies.get_dependencies_status)


@router.post("/setup/install-playwright")
async def api_install_playwright() -> dict[str, Any]:
    job_id = start_playwright_install_job()
    return {"job_id": job_id, "status": "running"}


@router.get("/setup/install-playwright/{job_id}")
async def api_install_playwright_status(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    if not job or job.get("kind") != "playwright_install":
        raise HTTPException(404, detail="job not found")
    payload = job_public_view(job_id, job)
    return {
        "job_id": job_id,
        "status": job.get("status"),
        "log": job.get("log") or [],
        "result": job.get("result"),
        "error": job.get("error"),
        "progress": payload.get("progress"),
    }


@router.post("/ingest/zhihu")
async def api_ingest_zhihu() -> dict[str, Any]:
    return await ingest.ingest_zhihu()


@router.get("/ingest/preflight")
async def api_ingest_preflight() -> dict[str, Any]:
    return await ingest.ingest_preflight()


@router.post("/ingest/accounts-sync")
async def api_ingest_accounts_sync() -> dict[str, Any]:
    """B站 + 知乎 Cookie API 一键拉取（与扩展「服务端拉取」相同）。"""
    return await ingest.ingest_accounts_sync()


@router.get("/ingest/browser-sync/status")
async def api_browser_sync_status() -> dict[str, Any]:
    return await browser_sync.browser_sync_status()


@router.post("/ingest/browser-sync")
async def api_ingest_browser_sync(body: BrowserSyncRequest | None = None) -> dict[str, Any]:
    """启动 Playwright 本机 Edge 会话补洞（后台 job）。"""
    req = body or BrowserSyncRequest()
    platforms = tuple(p for p in req.platforms if p in {"bilibili", "zhihu"}) or ("bilibili", "zhihu")
    kwargs: dict[str, Any] = {"platforms": platforms}
    if req.mode:
        kwargs["mode"] = req.mode
    if req.headless is not None:
        kwargs["headless"] = req.headless
    job_id = start_browser_sync_job(**kwargs)
    return {"job_id": job_id, "status": "running"}


@router.get("/ingest/browser-sync/{job_id}")
async def api_ingest_browser_sync_result(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, detail="job not found")
    if job["status"] == "running":
        return {"job_id": job_id, "status": "running"}
    if job["status"] == "error":
        raise HTTPException(500, detail=job["error"])
    return {"job_id": job_id, "status": "done", **(job.get("result") or {})}


@router.get("/ingest/health")
async def api_ingest_health() -> dict[str, Any]:
    return await health.get_health_status()


@router.post("/ingest/full-sync")
async def api_ingest_full_sync() -> dict[str, Any]:
    """统一同步：preflight → accounts-sync → browser-sync → 可选 AICU → 扩展 flush 提示。"""
    job_id = start_full_sync_job()
    return {"job_id": job_id, "status": "running"}


@router.get("/ingest/full-sync/{job_id}")
async def api_ingest_full_sync_result(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, detail="job not found")
    if job["status"] == "running":
        payload = job_public_view(job_id, job)
        return {
            "job_id": job_id,
            "status": "running",
            "steps": job.get("steps") or [],
            "progress": payload.get("progress"),
        }
    if job["status"] == "cancelled":
        return {
            "job_id": job_id,
            "status": "cancelled",
            "steps": job.get("steps") or [],
            "error": job.get("error") or "已取消",
        }
    if job["status"] == "error":
        raise HTTPException(500, detail=job["error"])
    result = job.get("result") or {}
    return {"job_id": job_id, "status": "done", "steps": result.get("steps") or job.get("steps") or [], **result}


@router.post("/ingest/full-sync/{job_id}/cancel")
async def api_ingest_full_sync_cancel(job_id: str) -> dict[str, Any]:
    if not await asyncio.to_thread(cancel_job, job_id):
        job = get_job(job_id)
        if not job:
            raise HTTPException(404, detail="job not found")
        if job.get("status") != "running":
            return {"job_id": job_id, "status": job.get("status"), "cancelled": False}
        raise HTTPException(409, detail="无法取消该任务")
    return {"job_id": job_id, "status": "cancelling", "cancelled": True}


@router.get("/ingest/likes")
@router.get("/ingest/recognition")
async def api_ingest_likes() -> dict[str, Any]:
    return await asyncio.to_thread(ingest.get_likes)


@router.get("/health/intl-reachability")
async def api_intl_reachability(force: bool = False) -> dict[str, Any]:
    from osint_toolkit.http.reachability import probe_international_reachability

    return await probe_international_reachability(force=force)


@router.post("/extension/events")
async def api_extension_events(body: ExtensionEventsRequest) -> dict[str, Any]:
    if body.version:
        await asyncio.to_thread(
            extension.ping_extension,
            version=body.version,
        )
    return await extension.ingest_extension_batch(body.events)


@router.post("/extension/ping")
async def api_extension_ping(body: ExtensionPingRequest) -> dict[str, Any]:
    return await asyncio.to_thread(
        extension.ping_extension,
        version=body.version,
        enabled=body.enabled,
        pending_queue=body.pending_queue,
        last_flush_error=body.last_flush_error,
    )


@router.get("/extension/status")
async def api_extension_status(lite: bool = False) -> dict[str, Any]:
    return await asyncio.to_thread(extension.get_extension_status, include_stats=not lite)


@router.get("/events/insights")
async def api_events_insights(refresh: bool = False, no_ai: bool = False) -> dict[str, Any]:
    from osint_toolkit.services import events_insights

    return await asyncio.to_thread(
        events_insights.get_behavior_insights, refresh=refresh, no_ai=no_ai
    )


@router.get("/events/recent")
async def api_events_recent(
    limit: int = 50,
    offset: int = 0,
    via: str | None = None,
    event_type: str | None = None,
    min_score: int = 0,
) -> dict[str, Any]:
    return await asyncio.to_thread(
        events.list_recent_events,
        limit=limit,
        offset=offset,
        via=via,
        event_type=event_type,
        min_score=min_score,
    )


@router.post("/persona/build")
async def api_persona_build(review: bool = False) -> dict[str, Any]:
    return await asyncio.to_thread(persona.build_persona, review=review)


@router.get("/persona")
async def api_persona() -> dict[str, Any]:
    return await asyncio.to_thread(persona.show_persona)


@router.get("/persona/status")
async def api_persona_status(auto_rebuild: bool = False) -> dict[str, Any]:
    return await persona.refresh_persona_status(auto_rebuild=auto_rebuild)


@router.post("/persona/dismiss-notice")
async def api_persona_dismiss_notice() -> dict[str, Any]:
    return await asyncio.to_thread(persona.dismiss_persona_notice)


@router.get("/persona/suggested-queries")
async def api_persona_suggested_queries(no_ai: bool = False) -> dict[str, Any]:
    return await asyncio.to_thread(persona.get_suggested_queries, no_ai=no_ai)


@router.post("/persona/rollback")
async def api_persona_rollback(body: PersonaRollbackRequest) -> dict[str, Any]:
    return await asyncio.to_thread(persona.rollback_persona, body.version)


@router.get("/runs")
async def api_runs(limit: int = 50) -> dict[str, Any]:
    import asyncio

    safe_limit = max(1, min(int(limit), 100))
    data = await asyncio.to_thread(runs.list_runs, limit=safe_limit)
    return {"runs": data}


@router.post("/runs/batch-delete")
async def api_runs_batch_delete(body: RunsBatchDeleteRequest) -> dict[str, Any]:
    from osint_toolkit.web.tasks import cancel_job, get_job

    deleted: list[str] = []
    skipped: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw_id in body.run_ids:
        run_id = str(raw_id or "").strip()
        if not run_id or run_id in seen:
            continue
        seen.add(run_id)
        try:
            run_id = _validated_run_id(run_id)
        except HTTPException as exc:
            errors.append({"run_id": run_id, "error": str(exc.detail)})
            continue
        job = get_job(run_id)
        if job and job.get("status") == "running":
            await asyncio.to_thread(cancel_job, run_id)
            skipped.append({"run_id": run_id, "reason": "was_running_cancelled"})
        try:
            await asyncio.to_thread(runs.delete_run, run_id)
            deleted.append(run_id)
        except FileNotFoundError:
            skipped.append({"run_id": run_id, "reason": "not_found"})
        except Exception as exc:  # noqa: BLE001
            errors.append({"run_id": run_id, "error": str(exc)})
    return {
        "deleted": deleted,
        "skipped": skipped,
        "errors": errors,
        "count": len(deleted),
    }


@router.post("/runs/cleanup")
async def api_runs_cleanup(body: RunsCleanupRequest) -> dict[str, Any]:
    result = await asyncio.to_thread(
        runs.cleanup_runs,
        older_than_days=body.older_than_days,
        keep_latest=body.keep_latest,
        statuses=body.statuses,
        dry_run=body.dry_run,
    )
    return result


@router.get("/runs/{run_id}")
async def api_run_detail(run_id: str, step: str | None = None) -> Any:
    import asyncio

    run_id = _validated_run_id(run_id)
    try:
        return await asyncio.to_thread(runs.show_run, run_id, step)
    except FileNotFoundError as exc:
        raise HTTPException(404, detail=str(exc)) from exc


@router.get("/runs/{run_id}/artifacts/{name}")
async def api_run_artifact(run_id: str, name: str) -> PlainTextResponse:
    run_id = _validated_run_id(run_id)
    try:
        content, media_type = await asyncio.to_thread(runs.get_run_artifact, run_id, name)
    except FileNotFoundError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    return PlainTextResponse(content, media_type=media_type)


@router.get("/runs/{run_id}/report/download")
async def api_run_report_download(run_id: str) -> Response:
    run_id = _validated_run_id(run_id)
    try:
        content, filename = await asyncio.to_thread(runs.get_run_report_export, run_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    return Response(
        content=content.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/runs/{run_id}")
async def api_run_delete(run_id: str) -> dict[str, Any]:
    from osint_toolkit.web.tasks import cancel_job, get_job

    run_id = _validated_run_id(run_id)
    job = get_job(run_id)
    if job and job.get("status") == "running":
        await asyncio.to_thread(cancel_job, run_id)
    try:
        await asyncio.to_thread(runs.delete_run, run_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    return {"run_id": run_id, "deleted": True}


@router.get("/ai/directives")
async def api_directives_get() -> dict[str, Any]:
    return await asyncio.to_thread(ai_config.get_directives)


@router.put("/ai/directives")
async def api_directives_put(body: DirectivesUpdate) -> dict[str, Any]:
    return await asyncio.to_thread(ai_config.update_directives, body.data)


@router.get("/ai/prompts")
async def api_prompts_list() -> dict[str, Any]:
    return {"prompts": await asyncio.to_thread(ai_config.list_prompts)}


@router.get("/ai/prompts/{name}")
async def api_prompt_get(name: str) -> dict[str, str]:
    name = _validated_prompt_name(name)
    return await asyncio.to_thread(ai_config.get_prompt, name)


@router.put("/ai/prompts/{name}")
async def api_prompt_put(name: str, body: PromptUpdate) -> dict[str, str]:
    name = _validated_prompt_name(name)
    return await asyncio.to_thread(ai_config.update_prompt, name, body.text)


@router.post("/ai/prompts/{name}/reset")
async def api_prompt_reset(name: str) -> dict[str, Any]:
    name = _validated_prompt_name(name)
    return await asyncio.to_thread(ai_config.reset_prompt, name)


@router.get("/auth/status")
async def api_auth_status(target: str = "all", live_probe: bool = False) -> dict[str, Any]:
    return {
        "items": await asyncio.to_thread(auth.get_auth_status, target, live_probe=live_probe),
    }


@router.get("/config/secrets")
async def api_config_secrets_list() -> dict[str, Any]:
    return await asyncio.to_thread(secrets.list_api_secrets)


@router.post("/config/secrets/{secret_id}")
async def api_config_secrets_save(secret_id: str, body: SecretSaveRequest) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(secrets.save_api_secret, secret_id, body.value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/config/secrets/{secret_id}/test")
async def api_config_secrets_test(secret_id: str) -> dict[str, Any]:
    return await asyncio.to_thread(secrets.test_api_secret, secret_id)


@router.get("/config/tunables")
async def api_config_tunables_list() -> dict[str, Any]:
    from osint_toolkit.services import tunable_config

    return await asyncio.to_thread(tunable_config.list_tunable_groups)


@router.patch("/config/tunables")
async def api_config_tunables_patch(body: TunablePatchRequest) -> dict[str, Any]:
    from osint_toolkit.services import tunable_config

    try:
        result = await asyncio.to_thread(tunable_config.patch_tunable_values, body.values)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if "search.max_concurrent_searches" in (body.values or {}):
        drain_search_queue()
    return result


@router.post("/auth/sync-cookies")
async def api_sync_cookies(body: SyncCookiesRequest) -> dict[str, Any]:
    result = await asyncio.to_thread(
        auth.sync_cookies, browser=body.browser, domains=body.domains or None
    )
    return {
        "browser": result.browser,
        "domains_synced": result.domains_synced,
        "cookie_counts": result.cookie_counts,
        "errors": result.errors,
        "output_dir": str(result.output_dir),
    }


@router.post("/auth/import-cookies")
async def api_import_cookies(body: ImportCookiesRequest) -> dict[str, Any]:
    """从浏览器扩展写入 Cookie（推荐 Edge 130+，无需管理员）。"""
    result = await asyncio.to_thread(
        auth.import_cookies,
        headers_by_domain=body.domains,
        browser=body.browser or "extension",
    )
    return {
        "browser": result.browser,
        "domains_synced": result.domains_synced,
        "cookie_counts": result.cookie_counts,
        "errors": result.errors,
        "output_dir": str(result.output_dir),
    }


@router.get("/auth/paths")
async def api_auth_paths() -> dict[str, Any]:
    return auth.get_paths()


@router.post("/research/trees")
async def api_research_create(body: ResearchTreeCreate) -> dict[str, Any]:
    tree = await asyncio.to_thread(create_tree, body.title, query=body.query)
    return {"tree": tree}


@router.get("/research/trees")
async def api_research_list(limit: int = 30) -> dict[str, Any]:
    return {"trees": await asyncio.to_thread(list_trees, limit=limit)}


@router.get("/research/trees/{tree_id}")
async def api_research_get(tree_id: str) -> dict[str, Any]:
    tree_id = _validated_tree_id(tree_id)
    try:
        return {"tree": await asyncio.to_thread(load_tree, tree_id)}
    except FileNotFoundError:
        raise HTTPException(404, detail="tree not found") from None


@router.get("/research/trees/{tree_id}/markmap")
async def api_research_markmap(tree_id: str) -> dict[str, Any]:
    tree_id = _validated_tree_id(tree_id)
    try:
        tree = await asyncio.to_thread(load_tree, tree_id)
    except FileNotFoundError:
        raise HTTPException(404, detail="tree not found") from None
    return {"markdown": tree_to_markmap(tree)}


@router.post("/research/trees/{tree_id}/nodes")
async def api_research_add_node(tree_id: str, body: ResearchNodeCreate) -> dict[str, Any]:
    tree_id = _validated_tree_id(tree_id)
    try:
        node = await asyncio.to_thread(
            add_node,
            tree_id,
            parent_id=body.parent_id,
            kind=body.kind,
            title=body.title or body.kind,
            run_id=body.run_id,
            payload=body.payload,
            meta=body.meta,
        )
    except FileNotFoundError:
        raise HTTPException(404, detail="tree not found") from None
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    return {"node": node}


@router.patch("/research/trees/{tree_id}/nodes/{node_id}")
async def api_research_patch_node(tree_id: str, node_id: str, body: ResearchNodePatch) -> dict[str, Any]:
    tree_id = _validated_tree_id(tree_id)
    try:
        node = await asyncio.to_thread(
            patch_node,
            tree_id,
            node_id,
            title=body.title,
            payload=body.payload,
            meta=body.meta,
        )
    except FileNotFoundError:
        raise HTTPException(404, detail="tree not found") from None
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    return {"node": node}


@router.delete("/research/trees/{tree_id}")
async def api_research_delete_tree(tree_id: str) -> dict[str, Any]:
    tree_id = _validated_tree_id(tree_id)
    try:
        await asyncio.to_thread(delete_tree, tree_id)
    except FileNotFoundError:
        raise HTTPException(404, detail="tree not found") from None
    return {"tree_id": tree_id, "deleted": True}


@router.patch("/research/trees/{tree_id}")
async def api_research_rename_tree(tree_id: str, body: ResearchTreeRename) -> dict[str, Any]:
    tree_id = _validated_tree_id(tree_id)
    try:
        tree = await asyncio.to_thread(rename_tree, tree_id, body.title)
    except FileNotFoundError:
        raise HTTPException(404, detail="tree not found") from None
    return {"tree": tree}


@router.delete("/research/trees/{tree_id}/nodes/{node_id}")
async def api_research_delete_node(tree_id: str, node_id: str) -> dict[str, Any]:
    tree_id = _validated_tree_id(tree_id)
    try:
        await asyncio.to_thread(delete_node, tree_id, node_id)
    except FileNotFoundError:
        raise HTTPException(404, detail="tree or node not found") from None
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    return {"node_id": node_id, "deleted": True}


@router.post("/research/suggest-queries")
async def api_research_suggest(body: ResearchSuggestRequest) -> dict[str, Any]:
    return await asyncio.to_thread(
        research_ai.suggest_queries,
        run_id=body.run_id,
        tree_id=body.tree_id,
    )


@router.post("/research/insight")
async def api_research_insight(body: ResearchInsightRequest) -> dict[str, Any]:
    result = await asyncio.to_thread(
        research_ai.generate_insight,
        tree_id=body.tree_id,
        run_id=body.run_id,
        parent_node_id=body.parent_node_id,
    )
    if not result.get("ok"):
        raise HTTPException(500, detail=result.get("error") or "insight failed")
    return result


@router.post("/research/trees/{tree_id}/summarize")
async def api_research_summarize_tree(tree_id: str) -> dict[str, Any]:
    tree_id = _validated_tree_id(tree_id)
    result = await asyncio.to_thread(research_ai.summarize_tree, tree_id)
    if not result.get("ok"):
        raise HTTPException(500, detail=result.get("error") or "summarize failed")
    return result


@router.get("/watches")
async def api_watches_list() -> dict[str, Any]:
    watches = await asyncio.to_thread(watch_service.load_watches)
    statuses = await asyncio.to_thread(
        lambda: [watch_service.watch_status(w) for w in watches]
    )
    return {"watches": statuses}


@router.post("/watches/{watch_id}/run")
async def api_watch_run(watch_id: str) -> dict[str, Any]:
    result = await watch_service.run_watch(watch_id)
    if not result.get("ok"):
        raise HTTPException(400, detail=result.get("error") or "watch run failed")
    return result


@router.get("/auth/domains")
async def api_auth_domains() -> dict[str, Any]:
    return {"domains": auth.list_domains()}


@router.get("/tools/domain/{domain}")
async def api_domain_lookup(domain: str) -> dict[str, Any]:
    try:
        assert_domain(domain)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await asyncio.to_thread(tools.lookup_domain, domain)
