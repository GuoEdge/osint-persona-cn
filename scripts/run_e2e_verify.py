"""快速复验（跳过完整同步，约 2 分钟）。"""

from __future__ import annotations

import os
import sys
import time

import httpx

BASE = os.environ.get("OSINT_WEB_BASE", "http://127.0.0.1:8787")


def step(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        sys.exit(1)


def wait_search(client: httpx.Client, run_id: str) -> dict:
    for _ in range(120):
        data = client.get(f"/api/search/{run_id}").json()
        if data.get("status") != "running":
            return data
        time.sleep(1)
    raise TimeoutError(run_id)


def main() -> None:
    with httpx.Client(base_url=BASE, timeout=httpx.Timeout(180.0)) as client:
        auth = {x["key"]: x for x in client.get("/api/auth/status").json()}
        step("Cookie", auth.get("bilibili", {}).get("ok") and auth.get("zhihu", {}).get("ok"))

        pre = client.get("/api/ingest/preflight").json()
        step("Preflight", pre.get("ready"), str(pre.get("hints", [])[:1]))

        sr = client.post(
            "/api/search",
            json={
                "query": "Python 异步",
                "sources": ["bilibili", "zhihu", "web", "v2ex"],
                "no_ai": True,
                "limit": 5,
                "mine_comments": True,
            },
        ).json()
        data = wait_search(client, sr["run_id"])
        items = data.get("items") or []
        by_src = {}
        for i in items:
            by_src[i.get("source")] = by_src.get(i.get("source"), 0) + 1
        step("搜罗", len(items) >= 3, f"items={len(items)} by_source={by_src} errors={data.get('source_errors')}")

        zh_items = [i for i in items if i.get("source") == "zhihu"]
        step("知乎结果", len(zh_items) >= 1 and zh_items[0].get("type") != "search_link", zh_items[0].get("url", "")[:60] if zh_items else "none")

        pb = client.post("/api/persona/build", params={"review": "false"})
        step("画像构建", pb.status_code == 200, str(pb.json().get("version")))

        persona = client.get("/api/persona").json()
        v = (persona.get("mental_model") or {}).get("version")
        snaps = persona.get("versions") or []
        step("版本快照", v >= 1 and len(snaps) >= 1, f"v={v} snapshots={snaps[-3:]}")

    print("\n=== 复验通过 ===")


if __name__ == "__main__":
    main()
