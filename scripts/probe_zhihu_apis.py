"""One-off Zhihu API probe (dev)."""
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from osint_toolkit.http.client import HttpClient


async def main() -> None:
    c = HttpClient()
    me = await c.get("https://www.zhihu.com/api/v4/me")
    token = me.json().get("url_token") or ""
    print("token", token)

    candidates = [
        f"/api/v4/members/{token}/activities?limit=20&include=data[*].target",
        "/api/v4/self/recent_viewed?offset=0&limit=10",
        "/api/v4/me/recent_viewed?offset=0&limit=10",
        "/api/v4/record_viewed_v2?offset=0&limit=10",
    ]
    for p in candidates:
        r = await c.get("https://www.zhihu.com" + p)
        body = r.text[:200].replace("\n", " ")
        print(r.status_code, p, body)

    r = await c.get("https://www.zhihu.com/recent-viewed")
    apis = re.findall(r'"(/api/v4/[^"]+)"', r.text)
    print("recent-viewed embedded apis:", apis[:10])


if __name__ == "__main__":
    asyncio.run(main())
