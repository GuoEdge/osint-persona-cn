"""异步 HTTP 客户端 / Async HTTP client with cookie injection."""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, quote, urlparse

import httpx

from osint_toolkit.auth.cookie_sync import cookie_header_for_url
from osint_toolkit.utils.config import load_config


class HttpClient:
    def __init__(self) -> None:
        cfg = load_config().get("http", {})
        self.timeout = float(cfg.get("timeout", 30))
        self.user_agent = str(
            cfg.get(
                "user_agent",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
            )
        )
        proxy = cfg.get("proxy")
        self._proxy = proxy if proxy else None

    def _headers(self, url: str) -> dict[str, str]:
        headers = {"User-Agent": self.user_agent}
        cookie = cookie_header_for_url(url)
        if cookie:
            headers["Cookie"] = cookie
        if "bilibili.com" in url:
            headers["Referer"] = "https://www.bilibili.com/"
            headers["Origin"] = "https://www.bilibili.com"
        elif "zhihu.com" in url:
            headers["Referer"] = self._zhihu_referer(url)
        elif "weixin.sogou.com" in url:
            headers["Referer"] = "https://weixin.sogou.com/"
        elif "mp.weixin.qq.com" in url:
            headers["Referer"] = "https://mp.weixin.qq.com/"
        return headers

    @staticmethod
    def _zhihu_referer(url: str) -> str:
        if "search_v3" in url:
            parsed = urlparse(url)
            q = (parse_qs(parsed.query).get("q") or [""])[0]
            if q:
                return f"https://www.zhihu.com/search?type=content&q={quote(q)}"
            return "https://www.zhihu.com/search?type=content"
        return "https://www.zhihu.com/"

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        headers = self._headers(url)
        extra = kwargs.pop("headers", None)
        if extra:
            headers = {**headers, **extra}
        async with httpx.AsyncClient(
            timeout=self.timeout,
            proxy=self._proxy,
            follow_redirects=True,
            trust_env=False,
        ) as client:
            return await client.get(url, headers=headers, **kwargs)

    async def get_text(self, url: str) -> str:
        resp = await self.get(url)
        resp.raise_for_status()
        return resp.text
