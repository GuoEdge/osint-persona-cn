import asyncio
import json
from osint_toolkit.http.client import HttpClient
from osint_toolkit.ingest.bilibili_account import _nav_mid
from osint_toolkit.ingest.bilibili_wbi import wbi_get

async def try_plain(client, url):
    r = await client.get(url)
    try:
        d = r.json()
        code = d.get("code")
        data = d.get("data") or {}
        items = data.get("list") or data.get("medias") or data.get("item") or []
        return r.status_code, code, len(items) if isinstance(items, list) else str(data)[:80]
    except Exception:
        return r.status_code, "non-json", r.text[:60]

async def main():
    client = HttpClient()
    mid = await _nav_mid(client)
    plain = [
        f"https://api.bilibili.com/x/v3/medialist/resource/list?type=3&oid={mid}&pn=1&ps=5",
        f"https://api.bilibili.com/x/v3/medialist/resource/list?type=3&mid={mid}&pn=1&ps=5",
        f"https://api.bilibili.com/x/v2/medialist?type=3&oid={mid}&pn=1&ps=5",
        f"https://api.bilibili.com/x/web-interface/wbi/like/archive/list?pn=1&ps=5",
    ]
    for u in plain:
        print("plain", u.split("?")[0].split("/")[-1], await try_plain(client, u))
    wbi_bases = [
        "https://api.bilibili.com/x/web-interface/wbi/like/archive/list",
        "https://api.bilibili.com/x/v3/medialist/resource/list",
    ]
    for base in wbi_bases:
        for params in [{"pn": 1, "ps": 5}, {"type": 3, "oid": mid, "pn": 1, "ps": 5}]:
            try:
                d = await wbi_get(client, base, params)
                data = d.get("data") or {}
                items = data.get("list") or data.get("medias") or []
                print("wbi", base.split("/")[-1], params, d.get("code"), len(items))
            except Exception as e:
                print("wbi err", base.split("/")[-1], e)

asyncio.run(main())
