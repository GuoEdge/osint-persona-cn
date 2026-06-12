"""Probe which social behavior APIs work with current cookies (read-only)."""

from __future__ import annotations

import asyncio
import json
import sys

from osint_toolkit.http.client import HttpClient


async def probe_raw(name: str, url: str) -> dict:
    client = HttpClient()
    try:
        resp = await client.get(url)
        text = resp.text[:300]
        ct = resp.headers.get("content-type", "")
        out = {"name": name, "status": resp.status_code, "content_type": ct}
        if "json" in ct or text.lstrip().startswith(("{", "[")):
            body = resp.json()
            out["body_preview"] = json.dumps(body, ensure_ascii=False)[:400]
            if name == "bilibili_watch_history":
                items = (body.get("data") or {}).get("list") or []
                out["count"] = len(items)
            elif name == "bilibili_nav_login":
                out["isLogin"] = (body.get("data") or {}).get("isLogin")
            elif name == "zhihu_vote_answers":
                out["count"] = len(body.get("data") or [])
            elif name == "bilibili_fav_folders":
                out["folders"] = len((body.get("data") or {}).get("list") or [])
        else:
            out["text_preview"] = text.replace("\n", " ")[:200]
        out["ok"] = resp.status_code == 200
        return out
    except Exception as exc:  # noqa: BLE001
        return {"name": name, "ok": False, "error": str(exc)}


async def main() -> int:
    urls = [
        ("bilibili_watch_history", "https://api.bilibili.com/x/web-interface/history/cursor?max=20"),
        ("bilibili_fav_folders", "https://api.bilibili.com/x/v3/fav/folder/list?type=2"),
        ("bilibili_archive_likes", "https://api.bilibili.com/x/web-interface/archive/likes?pn=1&ps=20"),
        ("zhihu_vote_answers", "https://www.zhihu.com/api/v4/members/me/vote_answers?offset=0&limit=20"),
        ("zhihu_favorites", "https://www.zhihu.com/api/v4/members/me/favorites?offset=0&limit=20"),
        ("bilibili_nav_login", "https://api.bilibili.com/x/web-interface/nav"),
    ]
    results = await asyncio.gather(*(probe_raw(n, u) for n, u in urls))
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
