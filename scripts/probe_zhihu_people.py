"""Probe Zhihu API reachability (diagnostic only; sync no longer uses dead endpoints)."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from osint_toolkit.http.client import HttpClient
from osint_toolkit.ingest.zhihu_account import _url_token
from osint_toolkit.ingest.zhihu_endpoint_registry import (
    DEPRECATED_ACTIVITY_ENDPOINTS,
    DEPRECATED_BROWSE_ENDPOINTS,
    DEPRECATED_VOTE_ENDPOINTS,
    PUBLISH_ENDPOINTS,
    paginate_member_api,
)


async def main() -> int:
    client = HttpClient()
    token = await _url_token(client)
    print("url_token", token)
    if not token:
        print("not logged in")
        return 1

    report: dict[str, object] = {
        "token": token,
        "note": "deprecated_* 仅供诊断；账号同步不再调用",
        "endpoints": {},
    }
    for label, specs in (
        ("votes_deprecated", DEPRECATED_VOTE_ENDPOINTS),
        ("browse_deprecated", DEPRECATED_BROWSE_ENDPOINTS),
        ("activities_deprecated", DEPRECATED_ACTIVITY_ENDPOINTS),
        ("publish", PUBLISH_ENDPOINTS),
    ):
        items, key = await paginate_member_api(client, token, specs, limit=5)
        report["endpoints"][label] = {"endpoint": key, "count": len(items)}

    out_path = Path.home() / ".osint" / "zhihu_probe.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("written", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
