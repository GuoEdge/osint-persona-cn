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

from osint_toolkit.pipeline.runner import PipelineRunner

from osint_toolkit.utils.config import get_search_config, load_config



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

    try:

        data = await coro

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


async def _mine_comments(

    items: list[IntelItem],

    *,

    top: int,

    no_ai: bool,

) -> list[dict[str, Any]]:

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
    if search_cfg.get("discover_aliases", True) and not no_ai:
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

    match_terms: list[str] = list(queries_used) + list(query_analysis.get("aliases") or [])

    collect_sources = [
        s for s in (query_analysis.get("recommended_sources") or sources) if s in COLLECTORS
    ]

    per_limit = per_query_limit(limit, len(queries_used))



    async def collect_all() -> dict[str, Any]:

        task_meta: list[tuple[str, str]] = []

        tasks = []

        for q in queries_used:

            for source_name in collect_sources:

                task_meta.append((source_name, q))

                tasks.append(_collect_source(source_name, q, per_limit))

        groups = await asyncio.gather(*tasks, return_exceptions=True)

        items: list[IntelItem] = []

        source_errors: list[dict[str, str]] = []
        for name in unknown_sources:
            source_errors.append({"source": name, "error": "未知来源（已忽略）", "query": query})

        for (source_name, q), group in zip(task_meta, groups, strict=False):

            if isinstance(group, Exception):

                source_errors.append({"source": source_name, "error": str(group), "query": q})

                continue

            if isinstance(group, list):

                for item in group:

                    matched = item.personal.get("matched_queries") or []

                    if q not in matched:

                        matched.append(q)

                    item.personal["matched_queries"] = matched

                items.extend(group)

        return {"items": items, "source_errors": source_errors}



    step_collect = await _record_step(

        runner,

        "collect_all",

        collect_all(),

        input_summary=f"queries={queries_used}, sources={collect_sources}, per_limit={per_limit}",

        artifact_name="items_raw.json",

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



    step_dedup = runner.run_step("dedup", dedup, artifact_name="items_dedup.json")

    items = step_dedup.data or []



    step_comments = await _record_step(

        runner,

        "mine_comments",

        _mine_comments(items, top=comment_mine_top, no_ai=no_ai),

        input_summary=f"top={comment_mine_top}",

        artifact_name="comments_mined.json",

        ai_invoked=not no_ai and comment_mine_top > 0,

    )

    _ = step_comments



    summaries = summarize_batch(

        items[: min(len(items), 15)],

        runtime_instruct=ai_instruct,

        no_ai=no_ai,

        persona_ctx=persona_ctx,

    )

    runner.run_step(

        "ai_summarize",

        lambda: summaries,

        ai_invoked=not no_ai,

        artifact_name="summaries.json",

    )



    simulations: list[dict] = []

    if not no_simulate:

        simulations = simulate_items(items, no_ai=no_ai, no_simulate=no_simulate)

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
    if search_cfg.get("discover_aliases", True) and not no_ai:
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


