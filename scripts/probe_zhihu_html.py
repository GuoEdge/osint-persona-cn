"""探测知乎 activities 页面 HTML 是否包含嵌入的动态数据（initialData）。"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from osint_toolkit.http.client import HttpClient


async def main() -> None:
    c = HttpClient()
    token = "sankichu"

    pages = [
        ("activities", f"https://www.zhihu.com/people/{token}/activities"),
        ("answers", f"https://www.zhihu.com/people/{token}/answers"),
        ("posts", f"https://www.zhihu.com/people/{token}/posts"),
        ("pins", f"https://www.zhihu.com/people/{token}/pins"),
        ("collections", f"https://www.zhihu.com/people/{token}/collections"),
        ("following", f"https://www.zhihu.com/people/{token}/following"),
    ]

    for label, url in pages:
        print(f"\n=== {label}: {url} ===")
        resp = await c.get(url, headers={"Referer": "https://www.zhihu.com/"})
        text = resp.text or ""
        print(f"status={resp.status_code} len={len(text)}")

        # 找 initialData
        m = re.search(r'<script id="js-initialData"[^>]*>(.*?)</script>', text, re.S)
        if not m:
            print("  NO initialData")
            for kw in ["initialData", "activities", "voteup", "赞同", "动态", "验证", "antispider", "412"]:
                if kw in text:
                    print(f"  found keyword: {kw}")
            tm = re.search(r"<title>(.*?)</title>", text, re.S)
            if tm:
                print(f"  title: {tm.group(1).strip()[:80]}")
            continue

        print("  FOUND initialData!")
        try:
            data = json.loads(m.group(1))
        except Exception as exc:
            print(f"  parse error: {exc}")
            continue

        print(f"  top keys: {list(data.keys())[:12]}")

        def find_interesting(obj, path=""):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    p = f"{path}.{k}" if path else k
                    if any(w in k.lower() for w in ("activ", "vote", "like", "pin", "answer", "article", "fav", "follow", "browse")):
                        if isinstance(v, list):
                            print(f"    {p}: list[{len(v)}]")
                            if v and isinstance(v[0], dict):
                                print(f"      first keys: {list(v[0].keys())[:8]}")
                                verb = v[0].get("verb") or v[0].get("type") or ""
                                print(f"      verb/type: {verb}")
                        elif isinstance(v, dict):
                            print(f"    {p}: dict keys={list(v.keys())[:6]}")
                    if isinstance(v, (dict, list)) and len(p.split(".")) < 4:
                        find_interesting(v, p)
            elif isinstance(obj, list):
                for i, item in enumerate(obj[:3]):
                    if isinstance(item, dict):
                        find_interesting(item, f"{path}[{i}]")

        find_interesting(data)

    # 也试试直接调 activities API 带不同 include 参数
    print("\n=== API: activities with various includes ===")
    includes = [
        "data[*].target,actor",
        "data[*].target,actor,origin",
        "data[*].target,is_normal,comment_count,voteup_count,created_time,updated_time",
        "",
    ]
    for inc in includes:
        q = f"limit=20&include={inc}" if inc else "limit=20"
        url = f"https://www.zhihu.com/api/v4/members/{token}/activities?{q}"
        resp = await c.get(url, headers={"Referer": f"https://www.zhihu.com/people/{token}/activities"})
        try:
            d = resp.json()
            data = d.get("data") or []
            print(f"  include={inc[:40]!r}: status={resp.status_code} items={len(data) if isinstance(data,list) else 'N/A'}")
            if isinstance(data, list) and data:
                print(f"    first: verb={data[0].get('verb')} type={data[0].get('type')}")
        except Exception:
            print(f"  include={inc[:40]!r}: status={resp.status_code} non-json")


if __name__ == "__main__":
    asyncio.run(main())
