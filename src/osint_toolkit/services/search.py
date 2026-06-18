"""搜索管线 / Search pipeline."""



from __future__ import annotations



import asyncio

import json

import os

from typing import Any



from osint_toolkit.ai.persona_sim import simulate_items

from osint_toolkit.ai.alias_discover import discover_aliases
from osint_toolkit.ai.query_expand import expand_query, per_query_limit

from osint_toolkit.ai.report import generate_report

from osint_toolkit.ai.summarize import summarize_batch

from osint_toolkit.analyzers.comments import summarize_comments

from osint_toolkit.analyzers.dedup import dedup_items

from osint_toolkit.analyzers.signals import apply_persona_boost, extract_signals

from osint_toolkit.persona.context import load_seen_urls, maybe_load_persona_context

from osint_toolkit.auth.cookie_sync import sync_browser_cookies

from osint_toolkit.collectors.bilibili import BilibiliCollector
from osint_toolkit.collectors.registry import COLLECTORS, DEFAULT_SEARCH_SOURCES, normalize_sources
from osint_toolkit.collectors.zhihu import ZhihuCollector

from osint_toolkit.exporters.report import export_report

from osint_toolkit.models.intel_item import IntelItem

from osint_toolkit.pipeline.context import RunContext

from osint_toolkit.pipeline.progress import JobCancelled, check_cancelled, update_progress

from osint_toolkit.pipeline.runner import PipelineRunner

from osint_toolkit.utils.config import get_search_config, load_config


_SOURCE_LABELS = {
    "zhihu": "知乎",
    "bilibili": "B站",
    "web": "网页",
    "v2ex": "V2EX",
    "rss": "RSS",
    "weixin": "微信",
}


def _source_label(name: str) -> str:
    return _SOURCE_LABELS.get(name, name)


def _collect_target_url(source: str, query: str) -> str:
    from urllib.parse import quote

    q = quote(query, safe="")
    urls = {
        "bilibili": f"https://search.bilibili.com/all?keyword={q}",
        "zhihu": f"https://www.zhihu.com/search?type=content&q={q}",
        "web": f"https://www.bing.com/search?q={q}",
        "v2ex": f"https://www.google.com/search?q=site:v2ex.com+{q}",
        "weixin": f"https://weixin.sogou.com/weixin?type=2&query={q}",
    }
    return urls.get(source, "")


def _preview_item(item: IntelItem) -> dict[str, Any]:
    rel = getattr(getattr(item, "signals", None), "relevance", 0) or 0
    return {
        "id": item.id,
        "source": item.source,
        "title": (item.title or "")[:120],
        "url": item.url,
        "relevance": round(float(rel), 2),
    }


def _recent_url_entries(items: list[Any], existing: list[dict[str, str]], *, limit: int = 5) -> list[dict[str, str]]:
    recent = list(existing or [])
    seen = {str(r.get("url") or "") for r in recent}
    for item in items:
        url = str(getattr(item, "url", "") or "")
        if not url.startswith("http") or url in seen:
            continue
        title = str(getattr(item, "title", "") or url)[:100]
        recent.insert(0, {"url": url, "title": title})
        seen.add(url)
        if len(recent) >= limit:
            break
    return recent[:limit]



async def _collect_source(name: str, query: str, limit: int) -> list[IntelItem]:

    cls = COLLECTORS.get(name)

    if not cls:

        return []

    return await cls().search(query, limit=limit)





async def _record_step(runner: PipelineRunner, name: str, coro, **kwargs: Any):

    import time



    start = time.perf_counter()

    issues: list[str] = []

    status = "ok"

    data: Any = None

    run_id = kwargs.get("run_id")

    progress_detail = str(kwargs.get("progress_detail") or "")

    if run_id:
        check_cancelled(run_id)
        update_progress(run_id, name, detail=progress_detail or f"正在执行 {name}…")

    try:

        data = await coro

    except JobCancelled:
        raise
    except Exception as exc:  # noqa: BLE001

        status = "error"

        issues.append(str(exc))

    duration_ms = int((time.perf_counter() - start) * 1000)

    artifact = kwargs.get("artifact_name")

    artifacts: list[str] = []

    artifact_payload: Any = data

    if isinstance(data, dict) and "items" in data:

        for err in data.get("source_errors") or []:

            issues.append(f"{err.get('source', '?')}: {err.get('error', '')}")

        artifact_payload = [i.to_dict() for i in data.get("items") or []]

    elif isinstance(data, list):

        if data and hasattr(data[0], "to_dict"):

            artifact_payload = [i.to_dict() for i in data]

        else:

            artifact_payload = data

    if artifact and data is not None:

        path = runner._write_artifact(artifact, artifact_payload)

        artifacts.append(path.name)

    from osint_toolkit.pipeline.runner import StepResult



    result = StepResult(

        step=name,

        status=status,

        duration_ms=duration_ms,

        input_summary=kwargs.get("input_summary", ""),

        output_summary=(

            f"{len(data.get('items', []))} items"

            if isinstance(data, dict) and "items" in data

            else (f"{len(data)} items" if isinstance(data, list) else "completed")

        ),

        issues=issues,

        artifacts=artifacts,

        ai_invoked=kwargs.get("ai_invoked", False),

        data=data,

    )

    step_payload = result.to_dict()

    if isinstance(data, dict) and data.get("source_errors"):

        step_payload["data"] = {"source_errors": data["source_errors"]}

    step_file = runner.run_dir / f"{len(runner.steps) + 1:02d}_{name}.json"

    step_file.write_text(json.dumps(step_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    runner._append_trace(result)

    if run_id:

        update_progress(

            run_id,

            name,

            detail=result.output_summary or "完成",

            mark_completed={

                "step": name,

                "duration_ms": duration_ms,

                "summary": result.output_summary,

                "status": status,

            },

        )

    return result





_COMMENT_SOURCES = ("bilibili", "zhihu")


def _allocate_comment_quota(sources: list[str], top: int) -> dict[str, int]:
    if not sources or top <= 0:
        return {}
    per = max(1, top // len(sources))
    quotas = {src: per for src in sources}
    remainder = top - per * len(sources)
    for idx in range(remainder):
        quotas[sources[idx]] += 1
    return quotas


def _comment_mine_top_for_source(source: str, default_top: int) -> int:
    if source != "zhihu":
        return default_top
    cfg = get_search_config()
    zh_top = cfg.get("zhihu_comment_mine_top")
    if zh_top is None:
        return default_top
    return max(0, int(zh_top))


def _effective_comment_top(default_top: int) -> int:
    cfg = get_search_config()
    zh_top = cfg.get("zhihu_comment_mine_top")
    if zh_top is None:
        return default_top
    return max(default_top, int(zh_top))


async def _mine_comments(

    items: list[IntelItem],

    *,

    top: int,

    no_ai: bool,

) -> list[dict[str, Any]]:

    top = _effective_comment_top(top)

    if top <= 0:

        return []

    collectors = {"bilibili": BilibiliCollector(), "zhihu": ZhihuCollector()}

    by_source: dict[str, list[IntelItem]] = {}

    for src in _COMMENT_SOURCES:

        candidates = sorted(

            [i for i in items if i.source == src],

            key=lambda i: i.signals.relevance,

            reverse=True,

        )

        if candidates:

            by_source[src] = candidates

    if not by_source:

        return []

    zhihu_top = _comment_mine_top_for_source("zhihu", top)
    if "zhihu" in by_source and zhihu_top != top:
        other_sources = [s for s in by_source if s != "zhihu"]
        other_top = max(0, top - zhihu_top) if other_sources else 0
        quotas = {"zhihu": zhihu_top}
        if other_sources and other_top > 0:
            quotas.update(_allocate_comment_quota(other_sources, other_top))
    else:
        quotas = _allocate_comment_quota(list(by_source.keys()), top)

    mined: list[dict[str, Any]] = []

    for src, quota in quotas.items():

        collector = collectors[src]

        for item in by_source[src][:quota]:

            if src == "bilibili" and item.type == "video":
                try:
                    await collector.enrich_video(item)
                except Exception:  # noqa: BLE001
                    pass

            if src == "zhihu" and item.type not in {"answer", "article"}:
                continue

            prefetched = item.personal.get("openapi_comments")
            if prefetched:
                comments = prefetched
            else:
                comments = await collector.fetch_comments(item.url)

            item.layers["comments"] = comments

            summary = await summarize_comments(comments, no_ai=no_ai)

            if summary:

                item.layers["comments_summary"] = summary

            mined.append(

                {

                    "item_id": item.id,

                    "source": src,

                    "url": item.url,

                    "title": item.title,

                    "comment_count": len(comments),

                    "comments_summary": summary,

                    "subtitle_kind": (item.layers.get("subtitle") or {}).get("kind"),

                    "danmaku_summary": item.layers.get("danmaku_summary", ""),

                }

            )

    return mined





async def run_search(

    query: str,

    *,

    sources: list[str] | None = None,

    limit: int = 10,

    digest: bool = False,

    trace: bool = False,

    profile: str = "default",

    ai_instruct: str = "",

    no_ai: bool = False,

    no_simulate: bool = False,

    disabled_ai_steps: list[str] | None = None,

    deep_top: int = 0,

    comment_mine_top: int | None = None,

    include_slurs: bool | None = None,

    run_id: str | None = None,

) -> dict[str, Any]:

    cfg = load_config()

    search_cfg = get_search_config()

    sources, unknown_sources = normalize_sources(sources, profile=profile)



    if comment_mine_top is None:

        comment_mine_top = int(search_cfg.get("comment_mine_top", 12))

    if deep_top > 0 and comment_mine_top == 0:

        comment_mine_top = deep_top



    update_progress(run_id, "starting", detail="检查 Cookie 与配置…")
    check_cancelled(run_id)

    if cfg.get("cookie_sync", {}).get("auto_sync_before_search") and os.name == "nt":

        try:

            sync_browser_cookies()

        except Exception:  # noqa: BLE001

            pass

    ctx_kwargs: dict[str, Any] = {

        "command": "search",

        "query": query,

        "profile": profile,

        "sources": sources,

        "trace": trace,

        "ai_instruct": ai_instruct,

        "no_ai": no_ai,

        "no_simulate": no_simulate,

        "disabled_ai_steps": disabled_ai_steps or [],

    }

    if run_id:

        ctx_kwargs["run_id"] = run_id

    ctx = RunContext(**ctx_kwargs)

    runner = PipelineRunner(ctx)

    persona_ctx = maybe_load_persona_context()



    discover_meta: dict[str, Any] = {}
    if search_cfg.get("discover_aliases", True):
        update_progress(run_id, "alias_discover", detail="联网发现关联词…")
        discover_meta = await discover_aliases(
            query,
            sources,
            no_ai=no_ai,
            include_slurs=include_slurs if include_slurs is not None else bool(search_cfg.get("include_slurs", True)),
            disabled_steps=disabled_ai_steps,
        )
        runner.run_step(
            "alias_discover",
            lambda: discover_meta,
            input_summary=f"query={query}, probe={discover_meta.get('probe_count', 0)}",
            artifact_name="alias_discover.json",
            ai_invoked="alias_discover" not in (disabled_ai_steps or []),
        )

    update_progress(run_id, "ai_query_analyze", detail="扩展查询词与来源…")
    query_analysis = expand_query(
        query,
        sources,
        persona_ctx,
        no_ai=no_ai,
        disabled_steps=disabled_ai_steps,
        include_slurs=include_slurs,
        discovered_aliases=discover_meta.get("discovered_aliases") or [],
        discover_meta=discover_meta,
    )

    runner.run_step(
        "ai_query_analyze",
        lambda: query_analysis,
        ai_invoked=not no_ai and "query_analyze" not in (disabled_ai_steps or []),
        artifact_name="query_analysis.json",
    )

    queries_used: list[str] = query_analysis.get("queries_used") or [query]

    match_terms: list[str] = list(queries_used)

    collect_sources = [
        s for s in (query_analysis.get("recommended_sources") or sources) if s in COLLECTORS
    ]

    per_limit = per_query_limit(limit, len(queries_used))

    collect_total = max(1, len(queries_used) * len(collect_sources))
    items_lock = asyncio.Lock()
    shared_items: list[IntelItem] = []
    zhihu_sem = asyncio.Semaphore(2)

    async def collect_all() -> dict[str, Any]:

        async def collect_one(source_name: str, q: str) -> tuple[str, str, list[IntelItem] | None, Exception | None]:
            short_q = q if len(q) <= 36 else q[:33] + "…"
            update_progress(
                run_id,
                "collect_all",
                detail=f"正在请求 {_source_label(source_name)} · {short_q}",
                current_url=_collect_target_url(source_name, q),
                current_source=source_name,
                current_query=q,
                collect_total=collect_total,
            )
            try:
                if source_name == "zhihu":
                    async with zhihu_sem:
                        group = await _collect_source(source_name, q, per_limit)
                else:
                    group = await _collect_source(source_name, q, per_limit)
                return source_name, q, group, None
            except Exception as exc:  # noqa: BLE001
                return source_name, q, None, exc

        task_meta: list[tuple[str, str]] = [
            (source_name, q) for q in queries_used for source_name in collect_sources
        ]
        pending = [collect_one(source_name, q) for source_name, q in task_meta]
        source_errors: list[dict[str, str]] = []
        for name in unknown_sources:
            source_errors.append({"source": name, "error": "未知来源（已忽略）", "query": query})

        import time

        collect_started = time.perf_counter()
        done = 0
        recent_urls: list[dict[str, str]] = []
        for finished in asyncio.as_completed(pending):
            check_cancelled(run_id)
            source_name, q, group, err = await finished
            done += 1
            short_q = q if len(q) <= 36 else q[:33] + "…"
            async with items_lock:
                items_found = len(shared_items)
            if err is not None:
                source_errors.append({"source": source_name, "error": str(err), "query": q})
            elif isinstance(group, list):
                for item in group:
                    for warning in item.personal.pop("collector_warnings", []) or []:
                        source_errors.append(
                            {"source": source_name, "error": f"警告: {warning}", "query": q}
                        )
                    matched = item.personal.get("matched_queries") or []
                    if q not in matched:
                        matched.append(q)
                    item.personal["matched_queries"] = matched
                async with items_lock:
                    shared_items.extend(group)
                    recent_urls = _recent_url_entries(group, recent_urls)
                    items_found = len(shared_items)

            elapsed = time.perf_counter() - collect_started
            eta_sec = int((elapsed / done) * (collect_total - done)) if done > 0 else None
            sample_url = ""
            if isinstance(group, list) and group:
                sample_url = str(group[0].url or "")
            preview_batch = [_preview_item(item) for item in (group or [])[:8]] if isinstance(group, list) else None
            update_progress(
                run_id,
                "collect_all",
                detail=f"{_source_label(source_name)} · {short_q}（{done}/{collect_total}）",
                collect_done=done,
                collect_total=collect_total,
                items_found=items_found,
                eta_sec=eta_sec,
                current_url=sample_url or _collect_target_url(source_name, q),
                recent_urls=recent_urls,
                partial_items_append=preview_batch,
            )

        return {"items": list(shared_items), "source_errors": source_errors}

    update_progress(
        run_id,
        "collect_all",
        detail=f"多源采集（共 {collect_total} 项）…",
        collect_done=0,
        collect_total=collect_total,
        items_found=0,
        eta_sec=None,
        current_url="",
    )

    step_collect = await _record_step(

        runner,

        "collect_all",

        collect_all(),

        input_summary=f"queries={queries_used}, sources={collect_sources}, per_limit={per_limit}",

        artifact_name="items_raw.json",

        run_id=run_id,

    )

    collect_data = step_collect.data if isinstance(step_collect.data, dict) else {"items": step_collect.data or []}

    items: list[IntelItem] = collect_data.get("items") or []

    source_errors: list[dict[str, str]] = collect_data.get("source_errors") or []



    seen_urls = load_seen_urls() if persona_ctx else set()



    def dedup() -> list[IntelItem]:

        deduped = dedup_items(items)

        for item in deduped:

            extract_signals(item, query, match_terms=match_terms)

            if persona_ctx and persona_ctx.recent_topics:

                apply_persona_boost(item, persona_ctx.recent_topics)

            if item.url and item.url in seen_urls:

                item.personal["already_seen"] = True

        return deduped



    update_progress(run_id, "dedup", detail="去重与相关度打分…", items_found=len(items))
    step_dedup = runner.run_step("dedup", dedup, artifact_name="items_dedup.json")

    items = step_dedup.data or []
    update_progress(run_id, "dedup", detail=f"去重后 {len(items)} 条", items_found=len(items))



    step_comments = await _record_step(

        runner,

        "mine_comments",

        _mine_comments(items, top=comment_mine_top, no_ai=no_ai),

        input_summary=f"top={comment_mine_top}",

        artifact_name="comments_mined.json",

        ai_invoked=not no_ai and comment_mine_top > 0,

        run_id=run_id,

        progress_detail=f"评论挖掘（top {comment_mine_top}）…" if comment_mine_top else "跳过评论挖掘",

    )

    _ = step_comments



    update_progress(run_id, "ai_summarize", detail="生成条目摘要…")
    summarize_top = int(search_cfg.get("ai_summarize_top", 15))
    summarize_extended = int(search_cfg.get("ai_summarize_extended", 35))
    primary_items = items[: min(len(items), summarize_top)]
    summaries = summarize_batch(
        primary_items,
        runtime_instruct=ai_instruct,
        no_ai=no_ai,
        persona_ctx=persona_ctx,
    )
    for item in items[summarize_top : min(len(items), summarize_extended)]:
        if not item.summary:
            text = (item.content or item.title or "").strip()
            item.summary = text[:320] + ("…" if len(text) > 320 else "")

    runner.run_step(

        "ai_summarize",

        lambda: summaries,

        ai_invoked=not no_ai,

        artifact_name="summaries.json",

    )



    sim_top = int(search_cfg.get("persona_sim_top", 20))
    simulations: list[dict] = []

    if not no_simulate:
        update_progress(run_id, "persona_simulate", detail="画像兴趣模拟…")
        simulations = simulate_items(items[: min(len(items), sim_top)], no_ai=no_ai, no_simulate=no_simulate)

        runner.run_step(

            "persona_simulate",

            lambda: simulations,

            ai_invoked=not no_ai and not no_simulate,

            artifact_name="simulations.json",

        )



    report_path = None

    report_text = ""

    sim_map = {s.get("item_id"): s for s in simulations if s.get("item_id")}



    def _sim_confidence(sim: dict) -> float:

        if sim.get("interest") != "interested":

            return 0.0

        try:

            return float(sim.get("confidence") or 0)

        except (TypeError, ValueError):

            return 0.0



    items.sort(

        key=lambda i: (

            i.signals.relevance

            + _sim_confidence(sim_map.get(i.id, {})) * 0.3

            + (0.15 if i.personal.get("already_seen") else 0.0)

        ),

        reverse=True,

    )



    if digest:
        update_progress(run_id, "ai_report", detail="撰写情报报告…")
        report_text = generate_report(

            query,

            items,

            run_id=ctx.run_id,

            runtime_instruct=ai_instruct,

            no_ai=no_ai,

            persona_brief=persona_ctx.brief if persona_ctx else "",

        )

        report_path = export_report(report_text, query=query, run_id=ctx.run_id)

        (ctx.ensure_run_dir() / "report.md").write_text(report_text, encoding="utf-8")



    return {

        "run_id": ctx.run_id,

        "items": items,

        "report": report_text,

        "report_path": str(report_path) if report_path else None,

        "simulations": simulations,

        "run_dir": str(ctx.ensure_run_dir()),

        "source_errors": source_errors,

        "query_analysis": query_analysis,

        "discover_meta": discover_meta,

        "queries_used": queries_used,

    }





async def preview_query_expansion(
    query: str,
    sources: list[str] | None = None,
    *,
    no_ai: bool = False,
    include_slurs: bool | None = None,
) -> dict[str, Any]:
    """Preview expanded queries without running full search."""
    persona_ctx = maybe_load_persona_context()
    sources, _unknown = normalize_sources(sources, profile="default")
    search_cfg = get_search_config()
    discover_meta: dict[str, Any] = {}
    if search_cfg.get("discover_aliases", True):
        discover_meta = await discover_aliases(
            query,
            sources,
            no_ai=no_ai,
            include_slurs=include_slurs if include_slurs is not None else bool(search_cfg.get("include_slurs", True)),
        )
    return expand_query(
        query,
        sources,
        persona_ctx,
        no_ai=no_ai,
        include_slurs=include_slurs,
        discovered_aliases=discover_meta.get("discovered_aliases") or [],
        discover_meta=discover_meta,
    )


