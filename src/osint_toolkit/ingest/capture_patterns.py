"""API 捕获 URL 正则（与 extension/content/inject.js 同构）。"""

from __future__ import annotations

import re

CAPTURE_URL_PATTERNS: tuple[str, ...] = (
    r"bilibili\.com/x/space/like/video",
    r"bilibili\.com/x/space/coin/video",
    r"bilibili\.com/x/web-interface/history",
    r"bilibili\.com/x/v3/fav/",
    r"bilibili\.com/x/v2/medialist",
    r"bilibili\.com/fav/resource/list",
    r"bilibili\.com/x/v2/reply/(wbi/)?main",
    r"bilibili\.com/x/v2/reply",
    r"bilibili\.com/x/relation/followings",
    r"bilibili\.com/x/web-interface/wbi/search",
    r"bilibili\.com/x/web-interface/search",
    r"bilibili\.com/x/web-interface/wbi/like",
    r"zhihu\.com/api/v4/search_v3",
    r"zhihu\.com/api/v4/.*collections.*items",
    r"zhihu\.com/api/v4/.*voteanswers",
    r"zhihu\.com/api/v4/.*vote_answers",
    r"zhihu\.com/api/v4/members/.*/activities",
    r"zhihu\.com/api/v4/members/.*/followees",
    r"zhihu\.com/api/v4/.*footprints",
    r"zhihu\.com/api/v4/.*browsing",
    r"zhihu\.com/api/v4/.*recent",
    r"zhihu\.com/api/v4/.*record_viewed",
    r"zhihu\.com/api/v4/.*viewed",
    r"mp\.weixin\.qq\.com/s\?",
    r"api\.github\.com/graphql",
)

_COMPILED = tuple(re.compile(p, re.I) for p in CAPTURE_URL_PATTERNS)


def should_capture_url(url: str) -> bool:
    return any(p.search(url) for p in _COMPILED)
