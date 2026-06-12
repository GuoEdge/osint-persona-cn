import asyncio, json
from osint_toolkit.http.client import HttpClient
from osint_toolkit.ingest.bilibili_account import _nav_mid
from osint_toolkit.ingest.bilibili_wbi import wbi_get
from osint_toolkit.ingest.zhihu_account import _url_token

async def bili():
    client = HttpClient()
    mid = await _nav_mid(client)
    urls = [
        f"https://api.bilibili.com/x/v2/medialist/resource/list?type=3&oid={mid}&business=archive&ps=5&pn=1",
        f"https://api.bilibili.com/x/v2/medialist/resource/list?type=3&oid={mid}&ps=5&pn=1",
        f"https://api.bilibili.com/x/space/wbi/arc/search?mid={mid}&ps=5&pn=1&order=pubdate&index=0",
    ]
    for u in urls:
        r = await client.get(u)
        print("b", u.split("?")[0].split("/")[-1], r.status_code)
        try:
            d = r.json()
            print(" ", d.get("code"), str(d.get("data"))[:120])
        except Exception:
            print(" ", r.text[:80])
    try:
        d = await wbi_get(client, "https://api.bilibili.com/x/space/wbi/arc/search", {"mid": mid, "ps": 5, "pn": 1, "order": "pubdate", "index": 0})
        print("wbi arc", d.get("code"), len((d.get("data") or {}).get("list") or {}).get("vlist") or []))
    except Exception as e:
        print("wbi arc err", e)
    for base, params in [
        ("https://api.bilibili.com/x/v2/medialist/resource/list", {"type": 3, "oid": mid, "business": "archive", "ps": 5, "pn": 1}),
        ("https://api.bilibili.com/x/web-interface/wbi/medialist/resource/list", {"type": 3, "oid": mid, "business": "archive", "ps": 5, "pn": 1}),
    ]:
        try:
            d = await wbi_get(client, base, params)
            data = d.get("data") or {}
            medias = data.get("medias") or data.get("list") or []
            print("wbi", base.split("/")[-1], d.get("code"), len(medias))
        except Exception as e:
            print("wbi", base.split("/")[-1], e)

async def zhihu():
    client = HttpClient()
    token = await _url_token(client)
    for u in [
        f"https://www.zhihu.com/api/v4/members/{token}/answers?include=data[*].is_normal,content&offset=0&limit=5",
        f"https://www.zhihu.com/api/v4/members/{token}?include=answer_count,voteup_count,following_count",
    ]:
        r = await client.get(u)
        print("z", u.split("?")[0].split("/")[-1], r.status_code)
        print(r.text[:400])

asyncio.run(bili())
asyncio.run(zhihu())
