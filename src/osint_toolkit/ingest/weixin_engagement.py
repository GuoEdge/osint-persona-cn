"""微信公众号文章互动数据解析 / WeChat article engagement parsing."""

from __future__ import annotations

import math
import re

_READ_PATTERNS = (
    re.compile(r"var\s+read_num\s*=\s*['\"]?(\d+)", re.I),
    re.compile(r'"read_num"\s*:\s*(\d+)', re.I),
    re.compile(r"read_num\s*:\s*['\"]?(\d+)", re.I),
    re.compile(r'id=["\']readNum\d*["\'][^>]*>\s*(\d+)', re.I),
    re.compile(r"阅读量\s*[:：]?\s*(\d+)", re.I),
)
_LIKE_PATTERNS = (
    re.compile(r"var\s+like_num\s*=\s*['\"]?(\d+)", re.I),
    re.compile(r'"like_num"\s*:\s*(\d+)', re.I),
    re.compile(r"like_num\s*:\s*['\"]?(\d+)", re.I),
)


def _first_int(patterns: tuple[re.Pattern[str], ...], text: str) -> int:
    for pat in patterns:
        match = pat.search(text)
        if match:
            try:
                return max(0, int(match.group(1)))
            except (TypeError, ValueError):
                continue
    return 0


def parse_weixin_engagement(html: str) -> dict[str, int]:
    """从 mp.weixin.qq.com 文章页 HTML 解析阅读量与在看数。"""
    chunk = (html or "")[:500_000]
    return {
        "views": _first_int(_READ_PATTERNS, chunk),
        "likes": _first_int(_LIKE_PATTERNS, chunk),
    }


def weixin_engagement_relevance_boost(views: int) -> float:
    """按阅读量对微信条目做对数加权。"""
    if views <= 0:
        return 0.0
    return min(0.22, math.log10(max(views, 1)) / 22.0)
