"""REST API 路由 / REST API routes."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse

from osint_toolkit.auth.paths import get_data_dir
from osint_toolkit.services import (
    ai_config,
    auth,
    browser_sync,
    digest,
    events,
    extension,
    feedback,
    health,
    ingest,
    knowledge,
    persona,
    runs,
    save,
    setup,
    tools,
)
from osint_toolkit.services import ingest_capabilities
from osint_toolkit.services import search as search_service
from osint_toolkit.services.ask import ask_question
from osint_toolkit.web.schemas import (
    AskRequest,
    BrowserSyncRequest,
    DirectivesUpdate,
    ExtensionEventsRequest,
    ExtensionPingRequest,
    FeedbackRequest,
    IngestAicuJsonRequest,
    IngestBrowserRequest,
    PersonaRollbackRequest,
    PromptUpdate,
    SaveRequest,
    SearchExpandRequest,
    SearchRequest,
    ImportCookiesRequest,
    SyncCookiesRequest,
)
from osint_toolkit.utils.config import load_sync_config
from osint_toolkit.web.tasks import get_job, get_job_result, start_browser_sync_job, start_full_sync_job, start_search_job

router = APIRouter(prefix="/api")


def _serialize_search_result(result: dict[str, Any]) -> dict[str, Any]:
    items = result.get("items") or []
    return {
        "run_id": result["run_id"],
        "items": [i.to_dict() if hasattr(i, "to_dict") else i for i in items],
        "report": result.get("report", ""),
        "report_path": result.get("report_path"),
        "simulations": result.get("simulations", []),
        "run_dir": result.get("run_dir"),
        "source_errors": result.get("source_errors") or [],
    }


@router.post("/search/expand")
async def api_search_expand(body: SearchExpandRequest) -> dict[str, Any]:
    return await search_service.preview_query_expansion(
        body.query,
        body.sources,
        no_ai=body.no_ai,
        include_slurs=body.include_slurs,
    )


@router.post("/search")
async def api_search(body: SearchRequest) -> dict[str, Any]:
    comment_mine_top = body.comment_mine_top
    if comment_mine_top is None:
        comment_mine_top = 12 if body.mine_comments else 0
    run_id = start_search_job(
        query=body.query,
        sources=body.sources,
        limit=body.limit,
        digest=body.digest,
        trace=body.trace,
        profile=body.profile,
        ai_instruct=body.ai_instruct,
        no_ai=body.no_ai,
        no_simulate=body.no_simulate,
        disabled_ai_steps=body.disabled_ai_steps,
        deep_top=body.deep_top,
        comment_mine_top=comment_mine_top,
        include_slurs=body.include_slurs,
    )
    return {"run_id": run_id, "status": "running"}


@router.get("/search/{run_id}")
async def api_search_result(run_id: str) -> dict[str, Any]:
    job = get_job(run_id)
    if job:
        if job["status"] == "running":
            return {"run_id": run_id, "status": "running"}
        if job["status"] == "error":
            raise HTTPException(500, detail=job["error"])
        return {"run_id": run_id, "status": "done", **_serialize_search_result(job["result"])}
    disk = get_job_result(run_id)
    if disk:
        payload = _serialize_search_result(disk)
        if disk.get("manifest"):
            payload["manifest"] = disk["manifest"]
        return {"run_id": run_id, "status": "done", **payload}
    raise HTTPException(404, detail="run not found")


@router.get("/search/{run_id}/events")
async def api_search_events(run_id: str) -> StreamingResponse:
    run_dir = get_data_dir() / "runs" / run_id

    async def event_stream():
        seen: set[str] = set()
        for _ in range(300):
            job = get_job(run_id)
            if run_dir.exists():
                for path in sorted(run_dir.glob("*_*.json")):
                    if path.name == "manifest.json" or path.name in seen:
                        continue
                    seen.add(path.name)
                    try:
                        data = json.loads(path.read_text(encoding="utf-8"))
                        payload = json.dumps({"type": "step", "file": path.name, "step": data}, ensure_ascii=False)
                        yield f"data: {payload}\n\n"
                        step_data = data.get("data") if isinstance(data, dict) else None
                        if isinstance(step_data, dict) and step_data.get("source_errors"):
                            err_payload = json.dumps(
                                {"type": "source_error", "errors": step_data["source_errors"]},
                                ensure_ascii=False,
                            )
                            yield f"data: {err_payload}\n\n"
                    except json.JSONDecodeError:
                        continue
            if job and job["status"] == "done":
                result = _serialize_search_result(job["result"])
                yield f"data: {json.dumps({'type': 'done', 'result': result}, ensure_ascii=False)}\n\n"
                break
            if job and job["status"] == "error":
                yield f"data: {json.dumps({'type': 'error', 'error': job['error']}, ensure_ascii=False)}\n\n"
                break
            yield f"data: {json.dumps({'type': 'ping'})}\n\n"
            await asyncio.sleep(1)
        else:
            yield f"data: {json.dumps({'type': 'timeout'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/save")
async def api_save(body: SaveRequest) -> dict[str, Any]:
    result = await save.save_url(body.url, with_comments=body.with_comments, no_ai=body.no_ai)
    return {"item": result["item"].to_dict(), "card_path": result["card_path"]}


@router.get("/knowledge/recall")
async def api_recall(q: str, limit: int = 20) -> dict[str, Any]:
    items = knowledge.recall(q, limit=limit)
    return {"items": [i.to_dict() for i in items], "count": len(items)}


@router.get("/knowledge/items")
async def api_knowledge_items(
    q: str = "",
    source: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    items = knowledge.list_items(query=q, source=source, limit=limit, offset=offset)
    return {
        "items": [i.to_dict() for i in items],
        "count": len(items),
        "total": knowledge.count_items(source=source),
    }


@router.post("/ask")
async def api_ask(body: AskRequest) -> dict[str, Any]:
    result = ask_question(body.question, run_id=body.run_id)
    if result.get("ok") is False:
        return result
    return result


@router.post("/feedback")
async def api_feedback(body: FeedbackRequest) -> dict[str, Any]:
    return feedback.submit_feedback(
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
    return {"feedback": feedback.get_feedback_map(ids or None)}


@router.get("/digest/daily")
async def api_digest_daily(ai: bool = False, no_ai: bool = False) -> dict[str, str]:
    return {"content": digest.get_daily_digest(use_ai=ai, no_ai=no_ai)}


@router.get("/digest/history")
async def api_digest_history(limit: int = 30) -> dict[str, Any]:
    return {"digests": digest.list_daily_digests(limit=limit)}


@router.get("/digest/reports")
async def api_digest_reports(limit: int = 50) -> dict[str, Any]:
    return {"reports": digest.list_reports(limit=limit)}


@router.post("/ingest/browser")
async def api_ingest_browser(body: IngestBrowserRequest) -> dict[str, Any]:
    return ingest.ingest_browser(since_days=body.since_days)


@router.post("/ingest/bilibili")
async def api_ingest_bilibili() -> dict[str, Any]:
    return await ingest.ingest_bilibili(include_favorites=True, include_likes=True)


@router.get("/ingest/bilibili-mid")
async def api_bilibili_mid() -> dict[str, Any]:
    return await ingest.bilibili_mid()


@router.get("/ingest/aicu-status")
async def api_aicu_status() -> dict[str, Any]:
    return ingest.aicu_status()


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
    return setup.get_setup_status()


@router.get("/setup/operations")
async def api_setup_operations() -> dict[str, Any]:
    from osint_toolkit.services import ops

    return ops.get_operations_runbook()


@router.get("/setup/sync-config")
async def api_setup_sync_config() -> dict[str, Any]:
    return load_sync_config()


@router.post("/setup/dismiss")
async def api_setup_dismiss() -> dict[str, Any]:
    setup.dismiss_setup()
    return {"ok": True}


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
        return {"job_id": job_id, "status": "running", "steps": job.get("steps") or []}
    if job["status"] == "error":
        raise HTTPException(500, detail=job["error"])
    result = job.get("result") or {}
    return {"job_id": job_id, "status": "done", "steps": result.get("steps") or job.get("steps") or [], **result}


@router.get("/ingest/likes")
async def api_ingest_likes() -> dict[str, Any]:
    return ingest.get_likes()


@router.post("/extension/events")
async def api_extension_events(body: ExtensionEventsRequest) -> dict[str, Any]:
    if body.version:
        extension.ping_extension(version=body.version)
    return await extension.ingest_extension_batch(body.events)


@router.post("/extension/ping")
async def api_extension_ping(body: ExtensionPingRequest) -> dict[str, Any]:
    return extension.ping_extension(version=body.version, enabled=body.enabled)


@router.get("/extension/status")
async def api_extension_status() -> dict[str, Any]:
    return extension.get_extension_status()


@router.get("/events/insights")
async def api_events_insights(refresh: bool = False, no_ai: bool = False) -> dict[str, Any]:
    from osint_toolkit.services import events_insights

    return events_insights.get_behavior_insights(refresh=refresh, no_ai=no_ai)


@router.get("/events/recent")
async def api_events_recent(
    limit: int = 50,
    offset: int = 0,
    via: str | None = None,
    event_type: str | None = None,
    min_score: int = 0,
) -> dict[str, Any]:
    return events.list_recent_events(
        limit=limit,
        offset=offset,
        via=via,
        event_type=event_type,
        min_score=min_score,
    )


@router.post("/persona/build")
async def api_persona_build(review: bool = False) -> dict[str, Any]:
    return persona.build_persona(review=review)


@router.get("/persona")
async def api_persona() -> dict[str, Any]:
    return persona.show_persona()


@router.get("/persona/status")
async def api_persona_status() -> dict[str, Any]:
    return await persona.refresh_persona_status()


@router.post("/persona/dismiss-notice")
async def api_persona_dismiss_notice() -> dict[str, Any]:
    return persona.dismiss_persona_notice()


@router.get("/persona/suggested-queries")
async def api_persona_suggested_queries(no_ai: bool = False) -> dict[str, Any]:
    return persona.get_suggested_queries(no_ai=no_ai)


@router.post("/persona/rollback")
async def api_persona_rollback(body: PersonaRollbackRequest) -> dict[str, Any]:
    return persona.rollback_persona(body.version)


@router.get("/runs")
async def api_runs(limit: int = 20) -> dict[str, Any]:
    return {"runs": runs.list_runs(limit=limit)}


@router.get("/runs/{run_id}")
async def api_run_detail(run_id: str, step: str | None = None) -> Any:
    try:
        return runs.show_run(run_id, step=step)
    except FileNotFoundError as exc:
        raise HTTPException(404, detail=str(exc)) from exc


@router.get("/runs/{run_id}/artifacts/{name}")
async def api_run_artifact(run_id: str, name: str) -> PlainTextResponse:
    try:
        content, media_type = runs.get_run_artifact(run_id, name)
    except FileNotFoundError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    return PlainTextResponse(content, media_type=media_type)


@router.get("/ai/directives")
async def api_directives_get() -> dict[str, Any]:
    return ai_config.get_directives()


@router.put("/ai/directives")
async def api_directives_put(body: DirectivesUpdate) -> dict[str, Any]:
    return ai_config.update_directives(body.data)


@router.get("/ai/prompts")
async def api_prompts_list() -> dict[str, Any]:
    return {"prompts": ai_config.list_prompts()}


@router.get("/ai/prompts/{name}")
async def api_prompt_get(name: str) -> dict[str, str]:
    return ai_config.get_prompt(name)


@router.put("/ai/prompts/{name}")
async def api_prompt_put(name: str, body: PromptUpdate) -> dict[str, str]:
    return ai_config.update_prompt(name, body.text)


@router.post("/ai/prompts/{name}/reset")
async def api_prompt_reset(name: str) -> dict[str, Any]:
    return ai_config.reset_prompt(name)


@router.get("/auth/status")
async def api_auth_status(target: str = "all") -> dict[str, Any]:
    return {"items": auth.get_auth_status(target)}


@router.post("/auth/sync-cookies")
async def api_sync_cookies(body: SyncCookiesRequest) -> dict[str, Any]:
    result = auth.sync_cookies(
        browser=body.browser,
        domains=body.domains or None,
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
    result = auth.import_cookies(
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


@router.get("/auth/domains")
async def api_auth_domains() -> dict[str, Any]:
    return {"domains": auth.list_domains()}


@router.get("/tools/domain/{domain}")
async def api_domain_lookup(domain: str) -> dict[str, Any]:
    return tools.lookup_domain(domain)
