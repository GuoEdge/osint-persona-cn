import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from osint_toolkit.http.client import HttpClient


async def main() -> None:
    c = HttpClient()
    r = await c.get("https://www.zhihu.com/recent-viewed")
    print("status", r.status_code, "len", len(r.text))
    for name, pat in [
        ("js-initialData", r'<script id="js-initialData"[^>]*>(.*?)</script>'),
        ("NEXT_DATA", r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>'),
    ]:
        m = re.search(pat, r.text, re.S)
        if m:
            data = json.loads(m.group(1))
            state = data.get("initialState") or {}
            print(name, "top keys", list(state.keys()))
            for k in state:
                if "recent" in k.lower() or "view" in k.lower() or "browse" in k.lower():
                    print("state key", k, str(state[k])[:300])
            print(json.dumps(state, ensure_ascii=False)[:2000])
            return
    print("no embedded json found")


if __name__ == "__main__":
    asyncio.run(main())
