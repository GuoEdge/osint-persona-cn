"""Probe zhihu vote endpoints."""
import asyncio
from osint_toolkit.http.client import HttpClient
from osint_toolkit.ingest.zhihu_account import _url_token

PATHS = [
    "/api/v4/members/{token}/answers/voted?offset=0&limit=20",
    "/api/v4/members/{token}/answers?offset=0&limit=20&sort_by=vote_num",
    "/api/v4/members/{token}/pins?offset=0&limit=20",
    "/api/v4/members/{token}/logs?offset=0&limit=20",
    "/api/v4/members/{token}/following-question-activities?offset=0&limit=20",
]

async def main():
    client = HttpClient()
    token = await _url_token(client)
    print("token", token)
    for p in PATHS:
        url = "https://www.zhihu.com" + p.format(token=token)
        r = await client.get(url)
        ct = r.headers.get("content-type", "")
        print(p.split("?")[0].split("/")[-1], r.status_code, len(r.text))
        if "json" in ct:
            d = r.json()
            data = d.get("data") or []
            print("  items", len(data) if isinstance(data, list) else list(d.keys())[:5])

asyncio.run(main())
