"""知乎公开页 URL 规范化 / Normalize Zhihu API URLs to browser-friendly links."""

from __future__ import annotations

import re
from typing import Any

_API_ARTICLE = re.compile(r"https?://api\.zhihu\.com/articles/(\d+)", re.I)
_API_ANSWER = re.compile(r"https?://api\.zhihu\.com/answers/(\d+)", re.I)
_API_QUESTION = re.compile(r"https?://api\.zhihu\.com/questions/(\d+)", re.I)
_API_ZVIDEO = re.compile(r"https?://api\.zhihu\.com/zvideos/(\d+)", re.I)


def public_zhihu_url(url: str, obj: dict[str, Any] | None = None) -> str:
    """将 api.zhihu.com 等内部链接转为可在浏览器打开的公开 URL。"""
    raw = str(url or "").strip()
    if not raw:
        return _url_from_object(obj)

    m = _API_ARTICLE.search(raw)
    if m:
        return f"https://zhuanlan.zhihu.com/p/{m.group(1)}"

    m = _API_ANSWER.search(raw)
    if m:
        aid = m.group(1)
        qid = _question_id(obj)
        if qid:
            return f"https://www.zhihu.com/question/{qid}/answer/{aid}"
        return f"https://www.zhihu.com/answer/{aid}"

    m = _API_QUESTION.search(raw)
    if m:
        return f"https://www.zhihu.com/question/{m.group(1)}"

    m = _API_ZVIDEO.search(raw)
    if m:
        return f"https://www.zhihu.com/zvideo/{m.group(1)}"

    if raw.startswith("http"):
        return raw

    built = _url_from_object(obj)
    return built or raw


def _question_id(obj: dict[str, Any] | None) -> str | None:
    if not obj:
        return None
    question = obj.get("question") or {}
    qid = question.get("id") or obj.get("question_id")
    if qid is not None:
        return str(qid)
    return None


def content_url_from_target(target: dict[str, Any], item: dict[str, Any] | None = None) -> str:
    """从知乎 API target/item 结构解析内容公开 URL。"""
    item = item or {}
    target = target or {}
    url = target.get("url") or item.get("url") or ""
    if url.startswith("http"):
        return public_zhihu_url(str(url), target)
    question = target.get("question") or {}
    answer_id = target.get("id")
    qid = question.get("id")
    if answer_id and qid:
        return f"https://www.zhihu.com/question/{qid}/answer/{answer_id}"
    if target.get("type") == "article" and target.get("id"):
        return f"https://zhuanlan.zhihu.com/p/{target['id']}"
    return str(url or "")


def _url_from_object(obj: dict[str, Any] | None) -> str:
    if not obj:
        return ""
    otype = str(obj.get("type") or obj.get("object_type") or "").lower()
    oid = obj.get("id")
    if otype == "article" and oid:
        return f"https://zhuanlan.zhihu.com/p/{oid}"
    if otype == "zvideo" and oid:
        return f"https://www.zhihu.com/zvideo/{oid}"
    if otype == "question" and oid:
        return f"https://www.zhihu.com/question/{oid}"
    if otype == "answer" and oid:
        qid = _question_id(obj)
        if qid:
            return f"https://www.zhihu.com/question/{qid}/answer/{oid}"
    return ""
