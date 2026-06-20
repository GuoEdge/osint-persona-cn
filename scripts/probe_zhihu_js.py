"""逆向知乎前端 JS：搜索 votedAnswers / voteAnswers / activities 相关 API 端点。"""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from osint_toolkit.http.client import HttpClient


async def main() -> None:
    c = HttpClient()

    # 1. 从 answers 页 HTML 提取 JS bundle URL
    print("=== 1. 提取 JS bundle URL ===")
    resp = await c.get("https://www.zhihu.com/people/sankichu/answers", headers={"Referer": "https://www.zhihu.com/"})
    html = resp.text or ""
    js_urls = re.findall(r'src="(https://static\.zhihu\.com/[^"]+\.js)"', html)
    # 也找内联的 main bundle
    js_urls += re.findall(r'"((?:https://static\.zhihu\.com/)?/heifetz/[^"]+\.js)"', html)
    js_urls = list(dict.fromkeys(js_urls))  # 去重保序
    print(f"  found {len(js_urls)} JS bundles")
    for u in js_urls[:10]:
        print(f"    {u}")

    # 2. 下载最大的几个 JS bundle，搜索关键词
    print("\n=== 2. 下载并搜索 JS bundle ===")
    keywords = [
        "voteAnswers", "votedAnswers", "voteanswers", "vote_answers",
        "answers/voted", "/voters", "voteup",
        "activities", "memberActivity",
        "likeHistory", "like_history",
        "myVotes", "my_votes",
    ]

    for js_url in js_urls[:8]:
        if not js_url.startswith("http"):
            js_url = "https://www.zhihu.com" + js_url if js_url.startswith("/") else "https://static.zhihu.com" + js_url
        try:
            resp = await c.get(js_url, timeout=30.0)
            js = resp.text or ""
            if len(js) < 1000:
                continue
            found_any = False
            for kw in keywords:
                if kw.lower() in js.lower():
                    if not found_any:
                        print(f"\n  --- {js_url.split('/')[-1]} ({len(js)} chars) ---")
                        found_any = True
                    # 找关键词上下文
                    for m in re.finditer(re.escape(kw), js, re.I):
                        start = max(0, m.start() - 80)
                        end = min(len(js), m.end() + 80)
                        ctx = js[start:end].replace("\n", " ").strip()
                        print(f"    [{kw}] ...{ctx}...")
                        break  # 每个关键词只显示第一个匹配
        except Exception as exc:
            print(f"  {js_url}: error {exc}")

    # 3. 直接搜 /api/v4/ 路径模式
    print("\n=== 3. 搜索 JS 中的 /api/v4/ 路径 ===")
    for js_url in js_urls[:5]:
        if not js_url.startswith("http"):
            js_url = "https://www.zhihu.com" + js_url if js_url.startswith("/") else "https://static.zhihu.com" + js_url
        try:
            resp = await c.get(js_url, timeout=30.0)
            js = resp.text or ""
            if len(js) < 1000:
                continue
            # 找所有 /api/v4/ 路径
            api_paths = re.findall(r'["\'](/api/v4/[^"\']{5,80})["\']', js)
            if api_paths:
                # 过滤出和 vote/activity/like 相关的
                interesting = [p for p in api_paths if any(w in p.lower() for w in ("vote", "activ", "like", "voted", "fav"))]
                if interesting:
                    print(f"\n  --- {js_url.split('/')[-1]} ---")
                    for p in sorted(set(interesting)):
                        print(f"    {p}")
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
