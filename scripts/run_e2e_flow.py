"""端到端业务流程检验 / End-to-end business flow runner."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx

BASE = os.environ.get("OSINT_WEB_BASE", "http://127.0.0.1:8787")
TIMEOUT = httpx.Timeout(300.0, connect=15.0)


def step(name: str, ok: bool, detail: str = "") -> None:
    tag = "PASS" if ok else "FAIL"
    msg = f"[{tag}] {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    if not ok:
        sys.exit(1)


def poll_job(client: httpx.Client, path: str, max_wait: int = 600) -> dict:
    for i in range(max_wait // 3):
        r = client.get(path)
        r.raise_for_status()
        data = r.json()
        status = data.get("status")
        if status == "running":
            steps = data.get("steps") or []
            if steps:
                last = steps[-1]
                print(f"  … {last.get('step')} ok={last.get('ok')}")
            time.sleep(3)
            continue
        return data
    raise TimeoutError(f"job timeout: {path}")


def wait_search(client: httpx.Client, run_id: str, max_wait: int = 120) -> dict:
    for _ in range(max_wait):
        r = client.get(f"/api/search/{run_id}")
        r.raise_for_status()
        data = r.json()
        if data.get("status") != "running":
            return data
        time.sleep(1)
    raise TimeoutError(f"search timeout run_id={run_id}")


def main() -> None:
    report: dict = {"steps": []}
    with httpx.Client(base_url=BASE, timeout=TIMEOUT) as client:
        # 1 auth
        auth = client.get("/api/auth/status").json()
        items = auth if isinstance(auth, list) else auth.get("items", [])
        auth_map = {x["key"]: x for x in items}
        bili_ok = auth_map.get("bilibili", {}).get("ok", False)
        zh_ok = auth_map.get("zhihu", {}).get("ok", False)
        step("Cookie 状态", bili_ok or zh_ok, f"bilibili={bili_ok}, zhihu={zh_ok}")
        report["steps"].append({"auth": auth_map})

        # 2 preflight
        pre = client.get("/api/ingest/preflight").json()
        step("Preflight", bool(pre.get("ready")), str(pre.get("hints", [])[:2]))
        report["steps"].append({"preflight": pre})

        # 3 health
        health = client.get("/api/ingest/health").json()
        step("健康检查 API", "events" in health, f"events={health.get('events', {}).get('total', 0)}")
        report["steps"].append({"health": {"ok": health.get("ok"), "blockers": health.get("blockers")} })

        # 4 full sync
        print("\n=== 完整同步（可能 2–8 分钟）===")
        start = client.post("/api/ingest/full-sync").json()
        job_id = start.get("job_id")
        step("启动 full-sync job", bool(job_id), job_id or "no job_id")
        sync_result = poll_job(client, f"/api/ingest/full-sync/{job_id}", max_wait=600)
        count = sync_result.get("count") or 0
        ok_sync = sync_result.get("status") == "done" and (sync_result.get("ok") or count > 0)
        step(
            "完整同步完成",
            ok_sync,
            f"count={count}, warnings={len(sync_result.get('warnings') or [])}",
        )
        report["steps"].append({"full_sync": sync_result})

        # 5 multi-source search
        print("\n=== 多源搜罗 + 评论挖掘 ===")
        sr = client.post(
            "/api/search",
            json={
                "query": "Python 异步编程",
                "sources": ["bilibili", "zhihu", "web", "v2ex"],
                "no_ai": True,
                "limit": 5,
                "mine_comments": True,
                "trace": True,
            },
        ).json()
        run_id = sr.get("run_id")
        step("启动搜索", bool(run_id), run_id or "")
        search_data = wait_search(client, run_id)
        items = search_data.get("items") or []
        source_errors = search_data.get("source_errors") or []
        step(
            "搜罗结果",
            len(items) >= 1,
            f"items={len(items)}, source_errors={len(source_errors)}",
        )
        if source_errors:
            print(f"  source_errors: {source_errors[:3]}")
        report["steps"].append({"search": {"items": len(items), "source_errors": source_errors}})

        # 6 save
        if items:
            url = items[0].get("url") or "https://www.python.org/about/"
        else:
            url = "https://www.python.org/about/"
        save = client.post("/api/save", json={"url": url, "with_comments": False, "no_ai": True})
        step("收录 save", save.status_code == 200, save.json().get("item", {}).get("title", "")[:60])

        # 7 persona
        print("\n=== 构建画像 ===")
        pb = client.post("/api/persona/build", params={"review": "false"})
        step("persona build", pb.status_code == 200, str(pb.json())[:120])
        persona = client.get("/api/persona").json()
        version = (persona.get("mental_model") or {}).get("version") or 0
        versions = persona.get("versions") or []
        step("persona 版本", version >= 1, f"version={version}, snapshots={len(versions)}")

        # 8 extension status
        ext = client.get("/api/extension/status").json()
        step("扩展状态 API", "connected" in ext, f"events={ext.get('extension_event_count', 0)}")

    out = Path.home() / ".osint" / "acceptance" / "e2e_flow.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== 全流程通过，报告: {out} ===")


if __name__ == "__main__":
    main()
