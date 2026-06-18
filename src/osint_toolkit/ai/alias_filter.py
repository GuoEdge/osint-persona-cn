"""关联词/扩展查询合法性过滤 / Filter noisy alias terms for search."""

from __future__ import annotations

import re

_DOMAIN_NOISE = re.compile(
    r"(https?:|www\.|\.com\b|\.cn\b|\.net\b|\.org\b|\.io\b|zhihu\.com|baidu\.com| › |›)",
    re.I,
)
_QUESTION_LIKE = re.compile(r"[？?]$")


def is_valid_search_term(term: str, *, query: str = "") -> bool:
    """Drop URL crumbs, SERP fragments, and over-long question titles."""
    t = str(term or "").strip()
    if not t or len(t) < 2 or len(t) > 24:
        return False
    if query and t.lower() == query.strip().lower():
        return False
    if _DOMAIN_NOISE.search(t):
        return False
    if "http" in t.lower():
        return False
    if "?" in t or "？" in t:
        return False
    if _QUESTION_LIKE.search(t) and len(t) > 8:
        return False
    if len(t) > 12 and re.search(r"(如何|什么|怎么|哪些|为什么|是指|优缺点)", t):
        return False
    if re.fullmatch(r"[\W_]+", t):
        return False
    return True
