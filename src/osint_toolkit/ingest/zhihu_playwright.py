"""知乎 Playwright 搜索 / Zhihu search via in-browser signed API."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from osint_toolkit.ingest.playwright_session import run_with_cookie_page


async def fetch_search_v3(query: str, limit: int = 10) -> dict[str, Any]:
    """在知乎页面上下文中调用 search_v3（由浏览器自动附带 x-zse-96）。"""
    search_url = f"https://www.zhihu.com/search?type=content&q={quote(query)}"

    async def _run(page: Any) -> dict[str, Any]:
        async with page.expect_response(
            lambda r: "search_v3" in r.url and r.status == 200,
            timeout=45_000,
        ) as resp_info:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=45_000)
        response = await resp_info.value
        return await response.json()

    return await run_with_cookie_page(_run, domains=["zhihu.com"])
