"""关联词/扩展查询合法性过滤 / Filter noisy alias terms for search."""

from __future__ import annotations

import re

_DOMAIN_NOISE = re.compile(
    r"(https?:|www\.|\.com\b|\.cn\b|\.net\b|\.org\b|\.io\b|zhihu\.com|baidu\.com| › |›)",
    re.I,
)
_QUESTION_LIKE = re.compile(r"[？?]$")
_NARROW_PRODUCT = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9.\-_\s]{0,30}$")
_BRAND_VERSION = re.compile(r"^([a-zA-Z]+)[\s.\-_]*(\d[\w.]*)$", re.I)
_TOKEN_SPLIT = re.compile(r"[\s.\-_:,/|｜]+")
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]{2,}")
_TIMESTAMP = re.compile(r"^\d{2}:\d{2}$")

_TECH_PRODUCT_QUERY = re.compile(
    r"composer|cursor|codex|copilot|claude|gemini|gpt|llm|mcp|agent|deepseek|glm|编程|模型|能力|开源",
    re.I,
)
_MUSIC_DRIFT_TERM = re.compile(
    r"音乐|作曲|编曲|写歌|歌曲|单曲|专辑|bgm|suno|udio",
    re.I,
)
_MUSIC_DRIFT_TERM_BOUND = re.compile(r"\b(?:ost|mv)\b", re.I)


def _music_drift_match(text: str) -> bool:
    return bool(_MUSIC_DRIFT_TERM.search(text) or _MUSIC_DRIFT_TERM_BOUND.search(text))

_GENERIC_NOISE = frozenset(
    {
        "字幕",
        "字幕:ai",
        "论文精读",
        "新智元导读",
        "中配",
        "速览",
        "万字长文",
        "合集",
        "导读",
        "学习",
        "康奈尔笔记法",
    }
)


def normalize_product_key(term: str) -> str:
    return re.sub(r"[\s.\-_:]+", "", str(term or "").lower())


def is_narrow_product_query(query: str) -> bool:
    """Short alphanumeric product/version queries like glm5.2, GPT-4."""
    q = query.strip()
    if not q or len(q) > 32 or not _NARROW_PRODUCT.match(q):
        return False
    has_letter = bool(re.search(r"[a-zA-Z]", q))
    has_digit = bool(re.search(r"\d", q))
    if has_letter and has_digit:
        return True
    return bool(re.fullmatch(r"[a-zA-Z]{2,12}", q)) and len(q) <= 6


def product_variants(query: str) -> list[str]:
    """Spelling variants for narrow product-version queries."""
    q = query.strip()
    if not is_narrow_product_query(q):
        return []
    compact = re.sub(r"\s+", "", q)
    raw: list[str] = [q, compact]
    m = _BRAND_VERSION.match(compact)
    if m:
        brand, ver = m.group(1), m.group(2)
        upper = brand.upper()
        raw.extend(
            [
                f"{upper}-{ver}",
                f"{upper}{ver}",
                f"{upper} {ver}",
                f"{brand}-{ver}",
                f"{brand}{ver}",
                f"{brand} {ver}",
            ]
        )
    seen_keys: set[str] = set()
    out: list[str] = []
    for term in raw:
        key = term.lower()
        if key in seen_keys:
            continue
        seen_keys.add(key)
        out.append(term)
    return out


def _dedupe_preserve_order(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for term in terms:
        t = term.strip()
        if not t:
            continue
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


def _extract_tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for part in _TOKEN_SPLIT.split(text.lower()):
        part = part.strip()
        if len(part) >= 2:
            tokens.add(part)
    for match in _CJK_RUN.finditer(text):
        tokens.add(match.group(0))
    return tokens


def _cjk_overlap(term: str, query: str) -> bool:
    t, q = term.strip(), query.strip()
    if len(t) >= 2 and len(q) >= 2:
        if t in q or q in t:
            return True
        t_chars = set(t)
        q_chars = set(q)
        shared = t_chars & q_chars
        if shared and len(shared) >= min(len(t_chars), len(q_chars)) * 0.5:
            return True
    return False


def has_relevance_to_query(term: str, query: str) -> bool:
    """True when an expanded term plausibly refers to the same subject as the query."""
    t = str(term or "").strip()
    q = str(query or "").strip()
    if not t or not q:
        return False
    if t.lower() == q.lower():
        return True
    if t.lower() in _GENERIC_NOISE:
        return False
    if _TIMESTAMP.match(t):
        return False
    if is_narrow_product_query(q):
        if re.fullmatch(r"\d[\d.]*", t):
            return False
        if len(t) <= 3 and normalize_product_key(t) not in normalize_product_key(q):
            return False
        tk, qk = normalize_product_key(t), normalize_product_key(q)
        if tk == qk or tk in qk or qk in tk:
            return True
        m_term = _BRAND_VERSION.match(re.sub(r"\s+", "", t))
        m_query = _BRAND_VERSION.match(re.sub(r"\s+", "", q))
        if m_term and m_query and m_term.group(1).lower() == m_query.group(1).lower():
            return True
        term_tokens = _extract_tokens(t)
        query_tokens = _extract_tokens(q)
        if term_tokens & query_tokens:
            return True
        return False

    tk, qk = normalize_product_key(t), normalize_product_key(q)
    if tk and qk and (tk == qk or tk in qk or qk in tk):
        return True

    term_tokens = _extract_tokens(t)
    query_tokens = _extract_tokens(q)
    if term_tokens & query_tokens:
        return True
    if _cjk_overlap(t, q):
        return True
    if len(q) >= 2 and len(t) >= 2 and (q.lower() in t.lower() or t.lower() in q.lower()):
        return True
    return False


def is_cross_script_pair(term: str, query: str) -> bool:
    t, q = str(term or "").strip(), str(query or "").strip()
    if not t or not q:
        return False
    latin_t = bool(re.search(r"[A-Za-z]{2,}", t))
    cjk_q = bool(_CJK_RUN.search(q))
    cjk_t = bool(_CJK_RUN.search(t))
    latin_q = bool(re.search(r"[A-Za-z]{2,}", q))
    return (latin_t and cjk_q) or (cjk_t and latin_q)


def is_music_drift_term(term: str, query: str) -> bool:
    """技术/产品查询被 AI 误扩为音乐领域检索词。"""
    q = (query or "").strip()
    t = (term or "").strip()
    if not q or not t:
        return False
    if not _music_drift_match(t):
        return False
    if _music_drift_match(q) or re.search(r"(歌|曲|music)", q, re.I):
        return False
    return bool(_TECH_PRODUCT_QUERY.search(q))


def filter_relevant_terms(terms: list[str], query: str, *, allow_cross_script: bool = False) -> list[str]:
    """Keep terms that overlap meaningfully with the original query."""
    q = query.strip()
    if not q:
        return _dedupe_preserve_order([str(t).strip() for t in terms if str(t).strip()])
    out: list[str] = []
    for term in terms:
        t = str(term).strip()
        if not t:
            continue
        if is_music_drift_term(t, q):
            continue
        if t.lower() == q.lower() or has_relevance_to_query(t, q):
            out.append(t)
        elif allow_cross_script and is_cross_script_pair(t, q):
            out.append(t)
    return _dedupe_preserve_order(out)


def is_valid_search_term(term: str, *, query: str = "", require_relevance: bool = False) -> bool:
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
    if t.lower() in _GENERIC_NOISE:
        return False
    if _TIMESTAMP.match(t):
        return False
    if require_relevance and query and not has_relevance_to_query(t, query):
        return False
    if is_music_drift_term(t, query):
        return False
    return True
