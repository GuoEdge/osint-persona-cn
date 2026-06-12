"""探测 AICU 是否可用 / Probe AICU availability."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from osint_toolkit.ingest.aicu import AICU_GETREPLY, _aicu_request_headers, _is_waf_block, get_bilibili_mid
from osint_toolkit.utils.config import load_config


async def probe_aicu() -> dict:
    cfg = load_config().get("ingest", {})
    if not cfg.get("aicu_enabled", False):
        return {"status": "DISABLE", "reason": "ingest.aicu_enabled 未开启"}

    mid = await get_bilibili_mid()
    if not mid:
        return {"status": "DISABLE", "reason": "B站未登录，无法探测 AICU"}

    import httpx

    headers = _aicu_request_headers()
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(
                AICU_GETREPLY,
                params={"uid": str(mid), "pn": "1", "ps": "5", "mode": "0", "keyword": ""},
                headers=headers,
            )
            text = resp.text[:500]
            if _is_waf_block(resp.status_code, text):
                return {
                    "status": "WAF_BLOCKED",
                    "reason": "AICU 被 WAF 拦截，建议使用 browser-sync 补洞",
                    "http_status": resp.status_code,
                }
            data = resp.json()
            replies = (data.get("data") or {}).get("replies") or []
            if data.get("code") not in (0, None):
                return {"status": "FAIL", "reason": data.get("message", "unknown"), "code": data.get("code")}
            return {"status": "PASS", "mid": mid, "sample_count": len(replies)}
        except json.JSONDecodeError:
            return {"status": "WAF_BLOCKED", "reason": "响应非 JSON，可能被 WAF 拦截"}
        except Exception as exc:  # noqa: BLE001
            return {"status": "FAIL", "reason": str(exc)}


def main() -> None:
    result = asyncio.run(probe_aicu())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("status") == "PASS":
        sys.exit(0)
    sys.exit(1 if result.get("status") == "FAIL" else 0)


if __name__ == "__main__":
    main()
