"""搜索管线 / Search pipeline."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from osint_toolkit.ai.persona_sim import simulate_items
from osint_toolkit.ai.report import generate_report
from osint_toolkit.ai.summarize import summarize_batch
from osint_toolkit.analyzers.dedup import dedup_items
from osint_toolkit.analyzers.signals import extract_signals
from osint_toolkit.auth.cookie_sync import sync_browser_cookies
from osint_toolkit.collectors.bilibili import BilibiliCollector
from osint_toolkit.collectors.rss import RssCollector
from osint_toolkit.collectors.v2ex import V2exCollector
from osint_toolkit.collectors.web import WebCollector
from osint_toolkit.collectors.zhihu import ZhihuCollector
from osint_toolkit.exporters.report import export_report
from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.pipeline.context import RunContext
from osint_toolkit.pipeline.runner import PipelineRunner
from osint_toolkit.utils.config import load_config

COLLECTORS = {
    "zhihu": ZhihuCollector,
    "bilibili": BilibiliCollector,
    "web": WebCollector,
    "v2ex": V2exCollector,
    "rss": RssCollector,
}


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
    if artifact and data is not None:
        path = runner._write_artifact(artifact, data if not isinstance(data, list) else [i.to_dict() for i in data])
        artifacts.append(path.name)
    from osint_toolkit.pipeline.runner import StepResult

    result = StepResult(
        step=name,
        status=status,
        duration_ms=duration_ms,
        input_summary=kwargs.get("input_summary", ""),
        output_summary=f"{len(data)} items" if isinstance(data, list) else "completed",
        issues=issues,
        artifacts=artifacts,
        ai_invoked=kwargs.get("ai_invoked", False),
        data=data,
    )
    step_file = runner.run_dir / f"{len(runner.steps) + 1:02d}_{name}.json"
    step_file.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    runner._append_trace(result)
    return result


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
) -> dict[str, Any]:
    cfg = load_config()
    profiles = cfg.get("profiles", {})
    prof = profiles.get(profile, {})
    sources = sources or prof.get("sources") or ["zhihu", "bilibili", "web"]
    if cfg.get("cookie_sync", {}).get("auto_sync_before_search") and os.name == "nt":
        try:
            sync_browser_cookies()
        except Exception:  # noqa: BLE001
            pass

    ctx = RunContext(
        command="search",
        query=query,
        profile=profile,
        sources=sources,
        trace=trace,
        ai_instruct=ai_instruct,
        no_ai=no_ai,
        no_simulate=no_simulate,
        disabled_ai_steps=disabled_ai_steps or [],
    )
    runner = PipelineRunner(ctx)

    async def collect_all() -> list[IntelItem]:
        groups = await asyncio.gather(*[_collect_source(s, query, limit) for s in sources], return_exceptions=True)
        items: list[IntelItem] = []
        for group in groups:
            if isinstance(group, list):
                items.extend(group)
        return items

    step_collect = await _record_step(
        runner,
        "collect_all",
        collect_all(),
        input_summary=f"query={query}, sources={sources}",
        artifact_name="items_raw.json",
    )
    items: list[IntelItem] = step_collect.data or []

    def dedup() -> list[IntelItem]:
        deduped = dedup_items(items)
        for item in deduped:
            extract_signals(item, query)
        return deduped

    step_dedup = runner.run_step("dedup", dedup, artifact_name="items_dedup.json")
    items = step_dedup.data or []

    summaries = summarize_batch(items[: min(len(items), 15)], runtime_instruct=ai_instruct, no_ai=no_ai)
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
    if digest:
        report_text = generate_report(
            query,
            items,
            run_id=ctx.run_id,
            runtime_instruct=ai_instruct,
            no_ai=no_ai,
        )
        report_path = export_report(report_text, query=query, run_id=ctx.run_id)
        (ctx.ensure_run_dir() / "report.md").write_text(report_text, encoding="utf-8")

    if deep_top > 0:
        bili = BilibiliCollector()
        for item in [i for i in items if i.source == "bilibili"][:deep_top]:
            comments = await bili.fetch_comments(item.url)
            item.layers["comments"] = comments

    return {
        "run_id": ctx.run_id,
        "items": items,
        "report": report_text,
        "report_path": str(report_path) if report_path else None,
        "simulations": simulations,
        "run_dir": str(ctx.ensure_run_dir()),
    }
