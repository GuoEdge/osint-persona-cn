"""SERP 抓取请求头 / Browser-like headers for HTML SERP scraping."""

from __future__ import annotations

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"
)


def serp_headers(url: str, *, user_agent: str | None = None) -> dict[str, str]:
    ua = user_agent or _BROWSER_UA
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }
    if "bing.com" in url:
        headers["Referer"] = "https://www.bing.com/"
    elif "baidu.com" in url:
        headers["Referer"] = "https://www.baidu.com/"
    elif "duckduckgo.com" in url:
        headers["Referer"] = "https://html.duckduckgo.com/"
    elif "sogou.com" in url:
        headers["Referer"] = "https://www.sogou.com/"
    return headers
