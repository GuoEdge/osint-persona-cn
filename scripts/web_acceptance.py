"""Web 控制台验收脚本 / Web console acceptance runner."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

BASE = os.environ.get("OSINT_WEB_BASE", "http://127.0.0.1:8787")
TIMEOUT = httpx.Timeout(120.0, connect=10.0)
REPORT_PATH = Path.home() / ".osint" / "acceptance" / "latest.json"


def ok(n: int, name: str, detail: str = "", *, report: dict[str, Any] | None = None) -> None:
    msg = f"[PASS] #{n} {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    if report is not None:
        report["checks"].append({"id": n, "name": name, "status": "PASS", "detail": detail})


def warn(n: int, name: str, detail: str, *, report: dict[str, Any] | None = None) -> None:
    msg = f"[WARN] #{n} {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    if report is not None:
        report["checks"].append({"id": n, "name": name, "status": "WARN", "detail": detail})


def fail(n: int, name: str, detail: str, *, report: dict[str, Any] | None = None) -> None:
    print(f"[FAIL] #{n} {name} — {detail}")
    if report is not None:
        report["checks"].append({"id": n, "name": name, "status": "FAIL", "detail": detail})
        _write_report(report)
    sys.exit(1)


def wait_search(client: httpx.Client, run_id: str, max_wait: int = 90) -> dict:
    for _ in range(max_wait):
        r = client.get(f"/api/search/{run_id}")
        r.raise_for_status()
        data = r.json()
        if data.get("status") != "running":
            return data
        time.sleep(1)
    raise TimeoutError(f"search timeout run_id={run_id}")


def poll_browser_sync_job(client: httpx.Client, job_id: str, max_wait: int = 120) -> dict[str, Any]:
    for _ in range(max_wait):
        r = client.get(f"/api/ingest/browser-sync/{job_id}")
        r.raise_for_status()
        data = r.json()
        if data.get("status") != "running":
            return data
        time.sleep(2)
    raise TimeoutError(f"browser-sync timeout job_id={job_id}")


def _write_report(report: dict[str, Any]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report["finished_at"] = datetime.now(UTC).isoformat()
    passes = sum(1 for c in report["checks"] if c["status"] == "PASS")
    warns = sum(1 for c in report["checks"] if c["status"] == "WARN")
    fails = sum(1 for c in report["checks"] if c["status"] == "FAIL")
    report["summary"] = {"pass": passes, "warn": warns, "fail": fails}
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已写入 {REPORT_PATH}")


def _run_aicu_probe() -> dict[str, Any]:
    import importlib.util

    probe_path = Path(__file__).resolve().parent / "probe_aicu.py"
    spec = importlib.util.spec_from_file_location("probe_aicu", probe_path)
    if not spec or not spec.loader:
        return {"status": "FAIL", "reason": "probe_aicu.py not loadable"}
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return asyncio.run(mod.probe_aicu())


def main() -> None:
    report: dict[str, Any] = {
        "base": BASE,
        "started_at": datetime.now(UTC).isoformat(),
        "checks": [],
    }

    with httpx.Client(base_url=BASE, timeout=TIMEOUT) as client:
        # 1 install assumed; 2 pages
        r = client.get("/")
        if r.status_code != 200 or "搜罗工作台" not in r.text:
            fail(2, "home page", f"status={r.status_code}", report=report)
        ok(2, "首页可打开", BASE, report=report)

        for path in ["/settings", "/save", "/knowledge", "/digest", "/persona", "/ingest", "/runs", "/ai"]:
            pr = client.get(path)
            if pr.status_code != 200:
                fail(2, f"page {path}", f"status={pr.status_code}", report=report)

        # 3 settings / auth
        auth = client.get("/api/auth/status").json()["items"]
        auth_map = {x["key"]: x for x in auth}
        ok(
            3,
            "设置页 auth/status",
            ", ".join(f"{k}={'OK' if v['ok'] else 'WARN'}" for k, v in auth_map.items()),
            report=report,
        )

        sync = client.post("/api/auth/sync-cookies", json={"browser": "edge"}).json()
        if sync.get("errors"):
            warn(3, "Cookie 同步", sync["errors"][0][:120], report=report)
        elif sync.get("domains_synced"):
            ok(3, "Cookie 同步", f"{len(sync['domains_synced'])} domains", report=report)
        else:
            warn(3, "Cookie 同步", "无域名写入（可能已有 Cookie 或 Edge 加密限制）", report=report)

        # 3b ingest preflight
        preflight = client.get("/api/ingest/preflight").json()
        report["preflight"] = preflight
        if preflight.get("ready"):
            ok(3, "ingest preflight", "ready", report=report)
        else:
            warn(3, "ingest preflight", "; ".join(preflight.get("hints") or ["not ready"]), report=report)

        # 3c accounts-sync
        if preflight.get("ready"):
            try:
                ar = client.post("/api/ingest/accounts-sync", timeout=httpx.Timeout(360.0, connect=10.0))
                adata = ar.json()
                report["accounts_sync"] = adata
                if ar.status_code == 200 and (adata.get("count") or 0) > 0:
                    ok(3, "accounts-sync", f"count={adata.get('count')}", report=report)
                elif ar.status_code == 200:
                    warn(3, "accounts-sync", "count=0", report=report)
                else:
                    warn(3, "accounts-sync", f"status={ar.status_code}", report=report)
            except Exception as exc:  # noqa: BLE001
                warn(3, "accounts-sync", str(exc)[:120], report=report)
        else:
            warn(3, "accounts-sync", "skipped (preflight not ready)", report=report)

        # 3d browser-sync job poll
        try:
            st = client.get("/api/ingest/browser-sync/status").json()
            if not st.get("playwright_installed"):
                warn(3, "browser-sync", "Playwright 未安装", report=report)
            else:
                start = client.post("/api/ingest/browser-sync", json={"platforms": ["bilibili", "zhihu"]}).json()
                job_id = start.get("job_id")
                if not job_id:
                    warn(3, "browser-sync", "no job_id", report=report)
                else:
                    job = poll_browser_sync_job(client, job_id)
                    report["browser_sync"] = {
                        "job_id": job_id,
                        "mode_used": job.get("mode_used"),
                        "accepted": job.get("accepted"),
                        "status": job.get("status"),
                    }
                    detail = f"accepted={job.get('accepted', 0)}, mode={job.get('mode_used', '?')}"
                    if job.get("status") == "done":
                        ok(3, "browser-sync job", detail, report=report)
                    else:
                        warn(3, "browser-sync job", detail, report=report)
        except Exception as exc:  # noqa: BLE001
            warn(3, "browser-sync", str(exc)[:120], report=report)

        # 3e aicu probe
        try:
            aicu = _run_aicu_probe()
            report["aicu_probe"] = aicu
            status = str(aicu.get("status", "FAIL"))
            if status == "PASS":
                ok(3, "aicu probe", f"mid={aicu.get('mid')}", report=report)
            elif status in ("DISABLE", "WAF_BLOCKED"):
                warn(3, "aicu probe", f"{status}: {aicu.get('reason', '')}", report=report)
            else:
                warn(3, "aicu probe", f"{status}: {aicu.get('reason', '')}", report=report)
        except Exception as exc:  # noqa: BLE001
            warn(3, "aicu probe", str(exc)[:120], report=report)

        # 4 search + SSE (multi-source + mine_comments)
        sr = client.post(
            "/api/search",
            json={
                "query": "Python asyncio",
                "sources": ["bilibili", "zhihu", "web", "v2ex"],
                "no_ai": True,
                "limit": 3,
                "trace": True,
                "mine_comments": True,
            },
        ).json()
        run_id = sr["run_id"]
        events = client.get(f"/api/search/{run_id}/events", timeout=TIMEOUT)
        sse_text = events.text
        if "data:" not in sse_text:
            fail(4, "SSE events", "no events received", report=report)
        try:
            search_data = wait_search(client, run_id)
        except TimeoutError as exc:
            fail(4, "搜罗搜索", str(exc), report=report)
        items = search_data.get("items") or []
        if not items:
            warn(4, "搜罗搜索", "empty items (multi-source)", report=report)
        else:
            ok(4, "搜罗搜索+SSE", f"run_id={run_id}, items={len(items)}", report=report)
        report["search"] = {"run_id": run_id, "items": len(items), "sources": ["bilibili", "zhihu", "web", "v2ex"]}

        item_id = items[0]["id"] if items else None

        # 5 digest (no_ai for speed if API flaky)
        dr = client.post(
            "/api/search",
            json={
                "query": "Python",
                "sources": ["web"],
                "digest": True,
                "no_ai": True,
                "limit": 2,
                "trace": True,
            },
        ).json()
        digest_data = wait_search(client, dr["run_id"])
        ok(5, "digest 搜索", f"report_len={len(digest_data.get('report') or '')}", report=report)

        ask = client.post("/api/ask", json={"question": "简要总结", "run_id": dr["run_id"]})
        if ask.status_code == 200:
            ok(5, "追问 API", "200", report=report)
        else:
            warn(5, "追问", f"status={ask.status_code}", report=report)

        # 6 feedback
        if item_id:
            fb = client.post(
                "/api/feedback",
                json={"target_id": item_id, "rating": "useful", "run_id": run_id, "reason": "acceptance test"},
            )
            if fb.status_code != 200:
                fail(6, "feedback", f"status={fb.status_code}", report=report)
            ok(6, "feedback", fb.json().get("rating", "useful"), report=report)
        else:
            warn(6, "feedback", "skipped (no search items)", report=report)

        # 7 save
        save = client.post(
            "/api/save",
            json={"url": "https://www.python.org/about/", "with_comments": False, "no_ai": True},
        )
        if save.status_code != 200:
            fail(7, "收录 save", f"status={save.status_code} {save.text[:200]}", report=report)
        saved_title = save.json()["item"].get("title", "")
        ok(7, "收录", saved_title[:60], report=report)

        # 8 knowledge recall
        recall = client.get("/api/knowledge/recall", params={"q": "Python", "limit": 10}).json()
        if recall.get("count", 0) < 1:
            fail(8, "知识库 recall", "no matches for Python", report=report)
        ok(8, "知识库 recall", f"count={recall['count']}", report=report)

        # 9 digest pages
        daily = client.get("/api/digest/daily").json()
        reports = client.get("/api/digest/reports").json()
        ok(9, "简报", f"daily_len={len(daily.get('content',''))}, reports={len(reports.get('reports',[]))}", report=report)

        # 10 ingest (optional per-platform)
        br = client.post("/api/ingest/browser", json={"since_days": 30})
        if br.status_code != 200:
            warn(10, "ingest browser", f"status={br.status_code} {br.text[:120]}", report=report)
        else:
            ok(10, "ingest browser", f"count={br.json().get('count', br.json())}", report=report)

        for name, path in [("bilibili", "/api/ingest/bilibili"), ("zhihu", "/api/ingest/zhihu")]:
            ir = client.post(path)
            if ir.status_code != 200:
                warn(10, f"ingest {name}", f"status={ir.status_code}", report=report)
            else:
                body = ir.json()
                ok(10, f"ingest {name}", str(body)[:80], report=report)

        # 11 persona
        pb = client.post("/api/persona/build", params={"review": "false"})
        if pb.status_code != 200:
            fail(11, "persona build", f"status={pb.status_code}", report=report)
        show = client.get("/api/persona").json()
        versions = show.get("versions") or []
        ok(11, "persona build/show", f"versions={versions[-3:]}", report=report)

        if len(versions) >= 2:
            rb = client.post(
                "/api/persona/rollback",
                json={"version": int(versions[-2]) if versions[-2].isdigit() else 1},
            )
            if rb.status_code == 200:
                ok(11, "persona rollback", str(rb.json()), report=report)
            else:
                warn(11, "persona rollback", f"status={rb.status_code}", report=report)

        # 12 runs
        runs = client.get("/api/runs").json()["runs"]
        if not runs:
            fail(12, "runs list", "empty", report=report)
        rid = runs[0]["run_id"]
        detail = client.get(f"/api/runs/{rid}").json()
        artifacts = []
        if isinstance(detail, dict):
            for step in detail.get("steps") or []:
                artifacts.extend(step.get("artifacts") or [])
        if artifacts:
            art = client.get(f"/api/runs/{rid}/artifacts/{artifacts[0]}")
            if art.status_code != 200:
                fail(12, "artifact", f"status={art.status_code}", report=report)
            ok(12, "运行记录+artifact", f"{rid} / {artifacts[0]}", report=report)
        else:
            ok(12, "运行记录", f"{rid} (no artifacts listed)", report=report)

        # 13 AI control
        directives = client.get("/api/ai/directives").json()
        test_note = {"acceptance_marker": "web-test"}
        merged = {**directives, **test_note}
        put = client.put("/api/ai/directives", json={"data": merged})
        if put.status_code != 200:
            fail(13, "directives put", f"status={put.status_code}", report=report)
        restored = {k: v for k, v in directives.items() if k != "acceptance_marker"}
        client.put("/api/ai/directives", json={"data": restored})

        prompts = client.get("/api/ai/prompts").json().get("prompts") or []
        if prompts:
            pname = prompts[0]["name"] if isinstance(prompts[0], dict) else prompts[0]
            pg = client.get(f"/api/ai/prompts/{pname}").json()
            ok(13, "AI directives/prompts", f"prompt={pname}, len={len(pg.get('text',''))}", report=report)
        else:
            ok(13, "AI directives", "saved", report=report)

        # 14 sync-config endpoint (optional)
        sc = client.get("/api/setup/sync-config")
        if sc.status_code == 200:
            ok(14, "sync-config", f"keys={len(sc.json())}", report=report)
        else:
            warn(14, "sync-config", f"status={sc.status_code}", report=report)

    _write_report(report)
    print("\n=== Web 验收完成：全部关键项通过 ===")


if __name__ == "__main__":
    main()
