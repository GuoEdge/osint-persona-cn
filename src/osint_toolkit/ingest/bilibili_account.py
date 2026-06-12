"""B站账号数据导入 / Bilibili account ingest."""

from __future__ import annotations

from osint_toolkit.http.client import HttpClient
from osint_toolkit.storage.knowledge import log_event


async def ingest_history(limit: int = 50) -> list[dict]:
    client = HttpClient()
    url = "https://api.bilibili.com/x/web-interface/history/cursor"
    results: list[dict] = []
    try:
        resp = await client.get(url)
        data = resp.json().get("data", {})
        for item in (data.get("list") or [])[:limit]:
            entry = {
                "source": "bilibili",
                "title": item.get("title", ""),
                "url": item.get("uri", "") or item.get("short_link_v2", ""),
                "progress": item.get("progress", 0),
                "duration": item.get("duration", 0),
            }
            log_event("bilibili_watch", entry)
            results.append(entry)
    except Exception:  # noqa: BLE001
        pass
    return results
