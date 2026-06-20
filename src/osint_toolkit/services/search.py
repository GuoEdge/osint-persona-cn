"""搜索管线 / Search pipeline."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from osint_toolkit.ai.alias_discover import discover_aliases
from osint_toolkit.ai.alias_filter import filter_relevant_terms, has_relevance_to_query, normalize_product_key
from osint_toolkit.ai.persona_sim import simulate_items
from osint_toolkit.ai.query_expand import expand_query, per_query_limit
from osint_toolkit.ai.report import generate_report
from osint_toolkit.ai.steering import is_step_enabled
from osint_toolkit.ai.summarize import summarize_batch
from osint_toolkit.analyzers.ai_relevance import refine_relevance_with_ai
from osint_toolkit.analyzers.citations import assign_citation_ids, build_citation_urls
from osint_toolkit.analyzers.comments import summarize_comments
from osint_toolkit.analyzers.dedup import dedup_items
from osint_toolkit.analyzers.signals import apply_persona_boost, extract_signals
from osint_toolkit.analyzers.zhihu_fetch_gate import (
    heuristic_zhihu_deep_plan,
    merge_comment_lists,
    plan_zhihu_deep_fetch,
)
from osint_toolkit.auth.cookie_sync import sync_browser_cookies
from osint_toolkit.collectors.bilibili import BilibiliCollector
from osint_toolkit.collectors.comment_mine_registry import COMMENT_MINE_SOURCES
from osint_toolkit.collectors.registry import (
    COLLECTORS,
    normalize_sources,
)
from osint_toolkit.collectors.source_catalog import get_source_labels
from osint_toolkit.collectors.thread_expand import enrich_forum_threads
from osint_toolkit.collectors.v2ex import V2exCollector
from osint_toolkit.collectors.zhihu import ZhihuCollector
from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.persona.context import load_seen_urls, maybe_load_persona_context
from osint_toolkit.pipeline.context import RunContext
from osint_toolkit.pipeline.progress import JobCancelled, check_cancelled, update_progress
from osint_toolkit.services.collect_tasks import build_fair_collect_tasks

_zhihu_collect_sem_cache: tuple[int, asyncio.Semaphore] | None = None


def _zhihu_global_collect_sem() -> asyncio.Semaphore:
    global _zhihu_collect_sem_cache
    from osint_toolkit.utils.config import get_search_config

    limit = max(1, int(get_search_config().get("zhihu_global_collect_sem", 2)))
    if _zhihu_collect_sem_cache is None or _zhihu_collect_sem_cache[0] != limit:
        _zhihu_collect_sem_cache = (limit, asyncio.Semaphore(limit))
    return _zhihu_collect_sem_cache[1]


def reset_zhihu_collect_sem_for_tests() -> None:
    global _zhihu_collect_sem_cache
    _zhihu_collect_sem_cache = None


from osint_toolkit.exporters.report import export_report
from osint_toolkit.pipeline.runner import PipelineRunner
from osint_toolkit.pipeline.timing_stats import (
    SearchEtaTracker,
    ingest_completed_run,
    planned_search_phases,
)
from osint_toolkit.utils.config import get_search_config, load_config

_SOURCE_LABELS = get_source_labels()


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
        "ithome": f"https://www.ithome.com/search?q={q}",
        "netease_music": f"https://music.163.com/#/search/m/?s={q}",
        "qq_music": f"https://y.qq.com/n/ryqq/search?w={q}",
        "kugou": f"https://www.kugou.com/yy/html/search.html#searchType=song&searchKey={q}",
        "douban": f"https://www.douban.com/search?q={q}",
        "sspai": f"https://sspai.com/search/post/{q}",
        "juejin": f"https://juejin.cn/search?query={q}",
        "kr36": f"https://www.36kr.com/search/articles/{q}",
        "huxiu": f"https://www.huxiu.com/search?s={q}",
        "solidot": f"https://www.solidot.org/search?tid=0&query={q}",
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


async def _collect_source(name: str, query: str, limit: int) -> tuple[list[IntelItem], list[str]]:
    cls = COLLECTORS.get(name)
    if not cls:
        return [], []
    collector = cls()
    items = await collector.search(query, limit=limit)
    orphan_warnings: list[str] = []
    if hasattr(collector, "consume_warnings"):
        warns = collector.consume_warnings()
        if warns:
            if items:
                items[0].personal.setdefault("collector_warnings", []).extend(warns)
            else:
                orphan_warnings = list(warns)
    return items, orphan_warnings


async def _record_step(runner: PipelineRunner, name: str, coro, **kwargs: Any):

    import time

    start = time.perf_counter()

    issues: list[str] = []

    status = "ok"

    data: Any = None

    run_id = kwargs.get("run_id")

    progress_detail = str(kwargs.get("progress_detail") or "")

    eta_tracker: SearchEtaTracker | None = kwargs.get("eta_tracker")

    eta_after_phase = kwargs.get("eta_after_phase")

    if run_id:
        check_cancelled(run_id)
        update_progress(run_id, name, detail=progress_detail or f"正在执行 {name}…")

    step_path = runner.begin_step(
        name,
        input_summary=kwargs.get("input_summary", ""),
        ai_invoked=bool(kwargs.get("ai_invoked", False)),
    )

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
        for warn in data.get("source_warnings") or []:
            issues.append(f"{warn.get('source', '?')}: {warn.get('warning') or warn.get('message', '')}")

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

    if isinstance(data, dict) and (data.get("source_errors") or data.get("source_warnings")):
        step_payload["data"] = {k: data[k] for k in ("source_errors", "source_warnings") if data.get(k)}

    step_file = step_path

    step_file.write_text(json.dumps(step_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    runner._append_trace(result)

    if run_id:
        extra_eta: dict[str, Any] = {}
        if eta_tracker:
            eta_tracker.mark_step_completed(name, duration_ms)
            next_phase = str(eta_after_phase or name)
            eta_val = eta_tracker.remaining_sec(current_phase=next_phase)
            if eta_val is not None:
                extra_eta["eta_sec"] = eta_val

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
            **extra_eta,
        )

    return result


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


def _apply_openapi_comment_layers(items: list[IntelItem]) -> None:
    """将 OpenAPI 预取评论写入 layers 作为预览；评论挖掘阶段可能再合并站内深抓结果。"""
    for item in items:
        if item.source != "zhihu":
            continue
        if item.layers.get("comments"):
            continue
        prefetched = item.personal.get("openapi_comments")
        if prefetched:
            item.layers["comments"] = prefetched


async def _enrich_short_zhihu_openapi(
    items: list[IntelItem],
    search_cfg: dict[str, Any],
    deep_plans: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    top = int(search_cfg.get("zhihu_openapi_deep_fetch_top", 5))
    if top <= 0:
        return []

    candidates: list[IntelItem] = []
    for item in items:
        if item.source != "zhihu" or not item.url:
            continue
        plan = (deep_plans or {}).get(item.id) or item.personal.get("deep_fetch_plan")
        if not plan:
            plan = heuristic_zhihu_deep_plan(item, search_cfg)
        if plan.get("fetch_body"):
            candidates.append(item)
    candidates.sort(key=lambda i: i.signals.relevance, reverse=True)
    candidates = candidates[:top]
    if not candidates:
        return []

    collector = ZhihuCollector()
    sem = _zhihu_global_collect_sem()
    enriched: list[dict[str, Any]] = []

    for item in candidates:
        try:
            async with sem:
                deeper = await collector.fetch(item.url)
            old_len = len((item.content or "").strip())
            new_content = (deeper.content or "").strip() if deeper else ""
            if new_content and len(new_content) > old_len:
                item.content = deeper.content
                if deeper.title:
                    item.title = deeper.title
                if deeper.author:
                    item.author = deeper.author
                if deeper.metrics:
                    item.metrics = deeper.metrics
                item.personal["body_deep_fetched"] = True
                enriched.append({"item_id": item.id, "url": item.url, "content_len": len(new_content)})
        except Exception:  # noqa: BLE001
            pass
    return enriched


async def _mine_comments(
    items: list[IntelItem],
    *,
    top: int,
    no_ai: bool,
    disabled_steps: list[str] | None = None,
    comment_mine_sources: list[str] | None = None,
    search_cfg: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    search_cfg = search_cfg or get_search_config()
    if not is_step_enabled("comment_mine", no_ai=no_ai, disabled_steps=disabled_steps):
        return []

    top = _effective_comment_top(top)

    if top <= 0:
        return []

    collectors: dict[str, Any] = {
        "bilibili": BilibiliCollector(),
        "zhihu": ZhihuCollector(),
        "v2ex": V2exCollector(),
    }

    by_source: dict[str, list[IntelItem]] = {}

    allowed_mine = set(comment_mine_sources) if comment_mine_sources else set(COMMENT_MINE_SOURCES)

    for src in COMMENT_MINE_SOURCES:
        if src not in allowed_mine:
            continue
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
        collector = collectors.get(src)
        if collector is None or not hasattr(collector, "fetch_comments"):
            continue
        for item in by_source[src][:quota]:
            if src == "bilibili" and item.type in {"video", "snippet"}:
                try:
                    if item.type == "snippet" and "BV" in item.url:
                        item.type = "video"
                    await collector.enrich_video(item)
                except Exception:  # noqa: BLE001
                    pass
            if src == "zhihu" and item.type not in {"answer", "article", "question"}:
                continue
            if src == "bilibili" and item.type not in {"video", "article", "snippet"}:
                continue

            if src == "zhihu":
                prefetched = list(item.personal.get("openapi_comments") or [])
                plan = item.personal.get("deep_fetch_plan") or heuristic_zhihu_deep_plan(item, search_cfg)
                fetched: list[dict[str, Any]] = []
                if plan.get("fetch_comments") and item.type in {"answer", "article"}:
                    try:
                        fetched = await collector.fetch_comments(item.url)
                        if fetched:
                            item.personal["comments_deep_fetched"] = True
                    except Exception:  # noqa: BLE001
                        fetched = []
                comments = merge_comment_lists(prefetched, fetched)
                item.personal["comment_fetch_plan"] = plan.get("reason") or ""
            else:
                comments = await collector.fetch_comments(item.url)

            item.layers["comments"] = comments
            summary = await summarize_comments(comments, no_ai=no_ai, disabled_steps=disabled_steps)

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
    source_overrides: dict[str, list[str]] | None = None,
    serp_fallback_accepted: list[str] | None = None,
    comment_mine_sources: list[str] | None = None,
) -> dict[str, Any]:

    cfg = load_config()

    search_cfg = get_search_config()

    sources, unknown_sources = normalize_sources(sources, profile=profile)

    if comment_mine_top is None:
        comment_mine_top = int(search_cfg.get("comment_mine_top", 12))

    if deep_top > 0 and comment_mine_top == 0:
        comment_mine_top = deep_top

    summarize_top = int(search_cfg.get("ai_summarize_top", 15))
    search_phases = planned_search_phases(
        discover_aliases=bool(search_cfg.get("discover_aliases", True)),
        comment_mine_top=comment_mine_top,
        digest=digest,
        no_simulate=no_simulate,
    )
    eta_tracker = SearchEtaTracker(
        phases=search_phases,
        task_meta=[],
        step_ctx={
            "comment_mine_top": comment_mine_top,
            "digest": digest,
            "no_simulate": no_simulate,
            "summarize_count": summarize_top,
        },
    )

    update_progress(run_id, "starting", detail="检查 Cookie 与配置…")
    check_cancelled(run_id)

    cookie_sync_warn: str | None = None
    if cfg.get("cookie_sync", {}).get("auto_sync_before_search") and os.name == "nt":
        try:
            await asyncio.to_thread(sync_browser_cookies)
        except Exception as exc:  # noqa: BLE001
            cookie_sync_warn = str(exc)
            update_progress(run_id, "starting", detail=f"Cookie 同步失败（继续搜罗）: {exc}")

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
        alias_eta = eta_tracker.remaining_sec(current_phase="alias_discover")
        update_progress(run_id, "alias_discover", detail="联网发现关联词…", eta_sec=alias_eta)
        step_discover = await _record_step(
            runner,
            "alias_discover",
            discover_aliases(
                query,
                sources,
                no_ai=no_ai,
                include_slurs=include_slurs
                if include_slurs is not None
                else bool(search_cfg.get("include_slurs", True)),
                disabled_steps=disabled_ai_steps,
            ),
            input_summary=f"query={query}",
            artifact_name="alias_discover.json",
            ai_invoked="alias_discover" not in (disabled_ai_steps or []),
            run_id=run_id,
            eta_tracker=eta_tracker,
            eta_after_phase="ai_query_analyze",
        )
        discover_meta = step_discover.data if isinstance(step_discover.data, dict) else {}

    intl_probe_terms: list[str] = []
    from osint_toolkit.ai.foreign_expand import foreign_expand_enabled, probe_foreign_aliases

    if foreign_expand_enabled(query, sources):
        try:
            intl_probe_terms = await probe_foreign_aliases(query, no_ai=no_ai)
        except Exception:  # noqa: BLE001
            intl_probe_terms = []

    update_progress(
        run_id,
        "ai_query_analyze",
        detail="扩展查询词…",
        eta_sec=eta_tracker.remaining_sec(current_phase="ai_query_analyze"),
    )
    analyze_path = runner.begin_step(
        "ai_query_analyze",
        ai_invoked=not no_ai and "query_analyze" not in (disabled_ai_steps or []),
    )
    update_progress(run_id, "ai_source_plan", detail="AI 链式分析话题与信源…")
    plan_path = runner.begin_step(
        "ai_source_plan",
        ai_invoked=not no_ai and "source_plan" not in (disabled_ai_steps or []),
    )
    query_analysis = await asyncio.to_thread(
        expand_query,
        query,
        sources,
        persona_ctx,
        no_ai=no_ai,
        disabled_steps=disabled_ai_steps,
        include_slurs=include_slurs,
        discovered_aliases=discover_meta.get("discovered_aliases") or [],
        discover_meta=discover_meta,
        intl_probe_terms=intl_probe_terms,
        profile=profile,
        source_overrides=source_overrides,
    )

    step_analyze = runner.run_step(
        "ai_query_analyze",
        lambda: {k: v for k, v in query_analysis.items() if k not in ("source_plan", "source_routing")},
        ai_invoked=not no_ai and "query_analyze" not in (disabled_ai_steps or []),
        artifact_name="query_analysis.json",
        step_path=analyze_path,
    )
    eta_tracker.mark_step_completed("ai_query_analyze", step_analyze.duration_ms)
    step_plan = runner.run_step(
        "ai_source_plan",
        lambda: {
            "source_plan": query_analysis.get("source_plan") or {},
            "source_routing": query_analysis.get("source_routing") or {},
            "active_sources": query_analysis.get("active_sources") or [],
        },
        ai_invoked=not no_ai and "source_plan" not in (disabled_ai_steps or []),
        artifact_name="source_plan.json",
        step_path=plan_path,
    )
    eta_tracker.mark_step_completed("ai_source_plan", step_plan.duration_ms)
    if run_id:
        update_progress(
            run_id,
            "ai_source_plan",
            detail="信源规划完成",
            eta_sec=eta_tracker.remaining_sec(current_phase="collect_all", collect_done=0),
        )

    queries_used: list[str] = query_analysis.get("queries_used") or [query]
    foreign_queries: list[str] = query_analysis.get("foreign_queries") or []
    queries_by_source: dict[str, list[str]] = dict(query_analysis.get("queries_by_source") or {})
    if search_cfg.get("strict_mode"):
        queries_used = filter_relevant_terms(queries_used, query)

    match_terms: list[str] = [query] + [q for q in queries_used if q != query and has_relevance_to_query(q, query)]

    collect_sources = list(query_analysis.get("active_sources") or query_analysis.get("recommended_sources") or sources)

    from osint_toolkit.services.source_preflight import apply_auth_gates

    auth_gate = apply_auth_gates(collect_sources, serp_fallback_accepted=serp_fallback_accepted or [])
    collect_sources = auth_gate["allowed_sources"] or list(sources)
    auth_preflight_warnings: list[dict[str, str]] = list(auth_gate.get("warnings") or [])

    per_limit = per_query_limit(limit, len(queries_used))
    max_collect_tasks = int(search_cfg.get("max_collect_tasks", 18))
    collect_timeout = float(search_cfg.get("collect_timeout_sec", 900))
    early_stop_items = int(search_cfg.get("collect_early_stop_items", 45))

    task_meta = build_fair_collect_tasks(
        queries_used,
        collect_sources,
        queries_by_source=queries_by_source or None,
        max_tasks=max_collect_tasks,
    )
    eta_tracker.set_task_meta(task_meta)

    collect_total = max(1, len(task_meta))
    items_lock = asyncio.Lock()
    shared_items: list[IntelItem] = []
    zhihu_sem = _zhihu_global_collect_sem()

    async def collect_all() -> dict[str, Any]:

        import time

        async def collect_one(
            source_name: str, q: str
        ) -> tuple[str, str, list[IntelItem] | None, list[str], Exception | None, float]:
            task_started = time.perf_counter()
            short_q = q if len(q) <= 36 else q[:33] + "…"
            update_progress(
                run_id,
                "collect_all",
                detail=f"正在请求 {_source_label(source_name)} · {short_q}",
                current_url=_collect_target_url(source_name, q),
                current_source=source_name,
                current_query=q,
                collect_total=collect_total,
                eta_sec=eta_tracker.remaining_sec(current_phase="collect_all", collect_done=done),
            )
            try:
                if source_name == "zhihu":
                    async with zhihu_sem:
                        group, orphan = await _collect_source(source_name, q, per_limit)
                else:
                    group, orphan = await _collect_source(source_name, q, per_limit)
                return source_name, q, group, orphan, None, time.perf_counter() - task_started
            except Exception as exc:  # noqa: BLE001
                return source_name, q, None, [], exc, time.perf_counter() - task_started

        task_meta_local = list(task_meta)
        pending = [asyncio.create_task(collect_one(source_name, q)) for source_name, q in task_meta_local]
        source_errors: list[dict[str, str]] = []
        source_warnings: list[dict[str, str]] = []
        source_warnings.extend(auth_preflight_warnings)
        if cookie_sync_warn:
            source_warnings.append({"source": "cookie_sync", "warning": cookie_sync_warn, "query": query})
        for name in unknown_sources:
            source_errors.append({"source": name, "error": "未知来源（已忽略）", "query": query})

        collect_started = time.perf_counter()
        done = 0
        recent_urls: list[dict[str, str]] = []
        stop_collect = False
        try:
            while pending and not stop_collect:
                check_cancelled(run_id)
                elapsed = time.perf_counter() - collect_started
                if elapsed >= collect_timeout:
                    for task in pending:
                        task.cancel()
                    source_warnings.append(
                        {"source": "*", "warning": f"采集超时 ({int(collect_timeout)}s)，已终止剩余任务", "query": query}
                    )
                    break
                wait_timeout = min(30.0, max(1.0, collect_timeout - elapsed))
                finished_set, pending = await asyncio.wait(
                    pending, timeout=wait_timeout, return_when=asyncio.FIRST_COMPLETED
                )
                if not finished_set:
                    continue
                for finished in finished_set:
                    if finished.cancelled():
                        continue
                    try:
                        source_name, q, group, orphan, err, task_duration = finished.result()
                    except Exception as exc:  # noqa: BLE001
                        source_errors.append({"source": "?", "error": str(exc), "query": query})
                        continue
                    eta_tracker.record_collect_task(source_name, task_duration)
                    for w in orphan:
                        source_warnings.append({"source": source_name, "warning": w, "query": q})
                    done += 1
                    short_q = q if len(q) <= 36 else q[:33] + "…"
                    async with items_lock:
                        items_found = len(shared_items)
                    if err is not None:
                        source_errors.append({"source": source_name, "error": str(err), "query": q})
                    elif isinstance(group, list):
                        for item in group:
                            for warning in item.personal.pop("collector_warnings", []) or []:
                                source_warnings.append({"source": source_name, "warning": warning, "query": q})
                            matched = item.personal.get("matched_queries") or []
                            if q not in matched:
                                matched.append(q)
                            item.personal["matched_queries"] = matched
                        async with items_lock:
                            shared_items.extend(group)
                            recent_urls = _recent_url_entries(group, recent_urls)
                            items_found = len(shared_items)

                    elapsed = time.perf_counter() - collect_started
                    eta_sec = eta_tracker.remaining_sec(current_phase="collect_all", collect_done=done)
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
                    if early_stop_items > 0 and items_found >= early_stop_items:
                        on_topic = sum(
                            1
                            for item in shared_items
                            if normalize_product_key(query) in normalize_product_key(item.title + item.content)
                            or query.lower() in (item.title + " " + item.content).lower()
                        )
                        if on_topic >= max(10, early_stop_items // 2):
                            stop_collect = True
                            for task in pending:
                                task.cancel()
                            source_warnings.append(
                                {
                                    "source": "*",
                                    "warning": f"已采集足够相关内容 ({items_found} 条)，提前结束",
                                    "query": query,
                                }
                            )
                            break
        finally:
            if pending:
                for task in pending:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)

        from osint_toolkit.utils.source_notices import consolidate_source_notices

        return {
            "items": list(shared_items),
            "source_errors": consolidate_source_notices(source_errors, text_key="error"),
            "source_warnings": consolidate_source_notices(source_warnings),
        }

    update_progress(
        run_id,
        "collect_all",
        detail=f"多源采集（共 {collect_total} 项）…",
        collect_done=0,
        collect_total=collect_total,
        items_found=0,
        eta_sec=eta_tracker.remaining_sec(current_phase="collect_all", collect_done=0),
        current_url="",
    )

    step_collect = await _record_step(
        runner,
        "collect_all",
        collect_all(),
        input_summary=f"queries={queries_used}, sources={collect_sources}, per_limit={per_limit}",
        artifact_name="items_raw.json",
        run_id=run_id,
        eta_tracker=eta_tracker,
        eta_after_phase="dedup",
    )

    collect_data = step_collect.data if isinstance(step_collect.data, dict) else {"items": step_collect.data or []}

    items: list[IntelItem] = collect_data.get("items") or []

    source_errors: list[dict[str, str]] = collect_data.get("source_errors") or []
    source_warnings: list[dict[str, str]] = collect_data.get("source_warnings") or []

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

    update_progress(
        run_id,
        "dedup",
        detail="去重与相关度打分…",
        items_found=len(items),
        eta_sec=eta_tracker.remaining_sec(current_phase="dedup"),
    )
    step_dedup = runner.run_step("dedup", dedup, artifact_name="items_dedup.json")
    eta_tracker.mark_step_completed("dedup", step_dedup.duration_ms)

    items = step_dedup.data or []
    new_count = sum(1 for i in items if not i.personal.get("already_seen"))
    intel_stats = {"new_count": new_count, "seen_count": max(0, len(items) - new_count), "total": len(items)}
    update_progress(run_id, "dedup", detail=f"去重后 {len(items)} 条（新增 {new_count}）", items_found=len(items))

    update_progress(
        run_id,
        "relevance_refine",
        detail="AI 辅助相关度精炼…",
        items_found=len(items),
        eta_sec=eta_tracker.remaining_sec(current_phase="relevance_refine"),
    )
    step_refine = await _record_step(
        runner,
        "relevance_refine",
        refine_relevance_with_ai(
            items,
            query,
            no_ai=no_ai,
            disabled_steps=disabled_ai_steps,
            search_cfg=search_cfg,
        ),
        input_summary=f"items={len(items)}",
        artifact_name="relevance_refine.json",
        ai_invoked=not no_ai
        and bool(search_cfg.get("ai_relevance_refine", True))
        and is_step_enabled("relevance_refine", no_ai=no_ai, disabled_steps=disabled_ai_steps),
        run_id=run_id,
        progress_detail="AI 辅助相关度…",
        eta_tracker=eta_tracker,
        eta_after_phase="dedup",
    )
    _ = step_refine

    thread_top = int(search_cfg.get("thread_expand_top", 5))
    if thread_top > 0:
        items = await enrich_forum_threads(items, top=thread_top)

    items.sort(key=lambda i: i.signals.relevance, reverse=True)

    zhihu_plan_pool = [i for i in items if i.source == "zhihu" and not i.signals.fold_reason]
    plan_limit = max(24, int(search_cfg.get("zhihu_openapi_deep_fetch_top", 5)) * 3)
    deep_plans = await plan_zhihu_deep_fetch(
        zhihu_plan_pool[:plan_limit],
        query,
        search_cfg,
        no_ai=no_ai,
        disabled_steps=disabled_ai_steps,
    )
    for item in zhihu_plan_pool:
        plan = deep_plans.get(item.id)
        if plan:
            item.personal["deep_fetch_plan"] = plan

    _apply_openapi_comment_layers(items)
    await _enrich_short_zhihu_openapi(items, search_cfg, deep_plans)

    items_for_mining = [i for i in items if not i.signals.fold_reason]
    step_comments = await _record_step(
        runner,
        "mine_comments",
        _mine_comments(
            items_for_mining,
            top=comment_mine_top,
            no_ai=no_ai,
            disabled_steps=disabled_ai_steps,
            comment_mine_sources=comment_mine_sources,
            search_cfg=search_cfg,
        ),
        input_summary=f"top={comment_mine_top}",
        artifact_name="comments_mined.json",
        ai_invoked=not no_ai
        and comment_mine_top > 0
        and is_step_enabled("comment_mine", no_ai=no_ai, disabled_steps=disabled_ai_steps),
        run_id=run_id,
        progress_detail=f"评论挖掘（top {comment_mine_top}）…" if comment_mine_top else "跳过评论挖掘",
        eta_tracker=eta_tracker,
        eta_after_phase="ai_summarize",
    )

    _ = step_comments

    update_progress(
        run_id,
        "ai_summarize",
        detail="生成条目摘要…",
        eta_sec=eta_tracker.remaining_sec(current_phase="ai_summarize"),
    )
    summarize_top = int(search_cfg.get("ai_summarize_top", 15))
    summarize_extended = int(search_cfg.get("ai_summarize_extended", 35))
    min_summarize_relevance = float(search_cfg.get("min_summarize_relevance", 0.25))
    primary_items = [
        item
        for item in items[: min(len(items), summarize_top)]
        if not item.signals.fold_reason and item.signals.relevance >= min_summarize_relevance
    ]
    summaries = await asyncio.to_thread(
        summarize_batch,
        primary_items,
        runtime_instruct=ai_instruct,
        no_ai=no_ai,
        disabled_steps=disabled_ai_steps,
        persona_ctx=persona_ctx,
    )
    for item in items[summarize_top : min(len(items), summarize_extended)]:
        if item.signals.fold_reason or item.signals.relevance < min_summarize_relevance:
            continue
        if not item.summary:
            text = (item.content or item.title or "").strip()
            item.summary = text[:320] + ("…" if len(text) > 320 else "")

    step_summarize = runner.run_step(
        "ai_summarize",
        lambda: summaries,
        ai_invoked=not no_ai,
        artifact_name="summaries.json",
    )
    eta_tracker.mark_step_completed("ai_summarize", step_summarize.duration_ms)
    if run_id:
        next_phase = "persona_simulate" if not no_simulate else ("ai_report" if digest else "ai_summarize")
        update_progress(
            run_id,
            "ai_summarize",
            detail="条目摘要完成",
            eta_sec=eta_tracker.remaining_sec(current_phase=next_phase),
        )

    sim_top = int(search_cfg.get("persona_sim_top", 20))
    simulations: list[dict] = []

    if not no_simulate:
        update_progress(
            run_id,
            "persona_simulate",
            detail="画像兴趣模拟…",
            eta_sec=eta_tracker.remaining_sec(current_phase="persona_simulate"),
        )
        simulations = await asyncio.to_thread(
            simulate_items,
            items[: min(len(items), sim_top)],
            no_ai=no_ai,
            no_simulate=no_simulate,
            disabled_steps=disabled_ai_steps,
        )

        step_sim = runner.run_step(
            "persona_simulate",
            lambda: simulations,
            ai_invoked=not no_ai and not no_simulate,
            artifact_name="simulations.json",
        )
        eta_tracker.mark_step_completed("persona_simulate", step_sim.duration_ms)

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

    citation_map = assign_citation_ids(items)

    try:
        final_path = ctx.ensure_run_dir() / "items_final.json"
        final_path.write_text(
            json.dumps([i.to_dict() for i in items], ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001
        pass

    if digest:
        update_progress(
            run_id,
            "ai_report",
            detail="撰写情报报告…",
            eta_sec=eta_tracker.remaining_sec(current_phase="ai_report"),
        )
        import time

        report_started = time.perf_counter()
        report_text = await asyncio.to_thread(
            generate_report,
            query,
            items,
            run_id=ctx.run_id,
            runtime_instruct=ai_instruct,
            no_ai=no_ai,
            persona_brief=persona_ctx.brief if persona_ctx else "",
            disabled_steps=disabled_ai_steps,
        )
        report_ms = int((time.perf_counter() - report_started) * 1000)

        report_path = export_report(report_text, query=query, run_id=ctx.run_id)

        (ctx.ensure_run_dir() / "report.md").write_text(report_text, encoding="utf-8")
        eta_tracker.mark_step_completed("ai_report", report_ms)

    ingest_completed_run(ctx.ensure_run_dir())

    from osint_toolkit.services.run_session import patch_manifest

    patch_manifest(
        ctx.run_id,
        item_count=len(items),
        source_error_count=len(source_errors),
        source_warning_count=len(source_warnings),
        step_count=len(runner.steps),
        queries_used=queries_used,
        collect_sources=collect_sources,
        profile=profile,
    )

    return {
        "run_id": ctx.run_id,
        "items": items,
        "report": report_text,
        "report_path": str(report_path) if report_path else None,
        "simulations": simulations,
        "run_dir": str(ctx.ensure_run_dir()),
        "source_errors": source_errors,
        "source_warnings": source_warnings,
        "intel_stats": intel_stats,
        "citation_map": citation_map,
        "citation_urls": build_citation_urls(items),
        "query_analysis": query_analysis,
        "source_plan": query_analysis.get("source_plan") or {},
        "source_routing": query_analysis.get("source_routing") or {},
        "collect_sources": collect_sources,
        "active_sources": collect_sources,
        "discover_meta": discover_meta,
        "queries_used": queries_used,
        "foreign_queries": foreign_queries,
        "queries_by_source": queries_by_source,
        "no_ai": no_ai,
    }


async def preview_query_expansion(
    query: str,
    sources: list[str] | None = None,
    *,
    no_ai: bool = False,
    include_slurs: bool | None = None,
    profile: str = "default",
    source_overrides: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Preview expanded queries without running full search."""
    persona_ctx = maybe_load_persona_context()
    sources, _unknown = normalize_sources(sources, profile=profile)
    search_cfg = get_search_config()
    discover_meta: dict[str, Any] = {}
    intl_probe_terms: list[str] = []
    if search_cfg.get("discover_aliases", True):
        discover_meta = await discover_aliases(
            query,
            sources,
            no_ai=no_ai,
            include_slurs=include_slurs if include_slurs is not None else bool(search_cfg.get("include_slurs", True)),
        )
    from osint_toolkit.ai.foreign_expand import foreign_expand_enabled, probe_foreign_aliases

    if foreign_expand_enabled(query, sources):
        try:
            intl_probe_terms = await probe_foreign_aliases(query, no_ai=no_ai)
        except Exception:  # noqa: BLE001
            intl_probe_terms = []
    return expand_query(
        query,
        sources,
        persona_ctx,
        no_ai=no_ai,
        include_slurs=include_slurs,
        discovered_aliases=discover_meta.get("discovered_aliases") or [],
        discover_meta=discover_meta,
        intl_probe_terms=intl_probe_terms,
        profile=profile,
        source_overrides=source_overrides,
    )
