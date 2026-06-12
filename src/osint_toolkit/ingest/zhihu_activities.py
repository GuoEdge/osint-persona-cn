"""知乎动态/活动流解析 / Zhihu activity stream parsing."""

from __future__ import annotations

from typing import Any


def iter_api_data_items(data: Any) -> list[dict[str, Any]]:
    """Normalize Zhihu-style API `data` fields that may be a list or paging object."""
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("data", "list", "items", "results"):
            nested = data.get(key)
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
    return []


def _zhihu_people_url(member: dict) -> str:
    token = str(member.get("url_token") or "")
    if token:
        return f"https://www.zhihu.com/people/{token}"
    return ""


def _zhihu_content_url(target: dict, item: dict | None = None) -> str:
    item = item or {}
    target = target or {}
    url = target.get("url") or item.get("url") or ""
    if url.startswith("http"):
        return url
    question = target.get("question") or {}
    answer_id = target.get("id")
    qid = question.get("id")
    if answer_id and qid:
        return f"https://www.zhihu.com/question/{qid}/answer/{answer_id}"
    if target.get("type") == "article" and target.get("id"):
        return f"https://zhuanlan.zhihu.com/p/{target['id']}"
    return url


def classify_activity(item: dict[str, Any]) -> tuple[str, str] | None:
    """Return (event_type, event_kind) or None if unsupported."""
    if not isinstance(item, dict):
        return None
    verb = str(item.get("verb") or "")
    typ = str(item.get("type") or "").upper()
    text = f"{verb} {typ}".lower()
    if any(k in text for k in ("赞", "vote", "upvote", "voteup")):
        return "zhihu_vote", "answer_vote"
    if any(k in text for k in ("收藏", "fav", "collect")):
        return "zhihu_fav", "activity_favorite"
    if any(k in text for k in ("关注", "follow")):
        return "zhihu_follow", "follow"
    if any(k in text for k in ("浏览", "browse", "view", "阅读")):
        return "zhihu_browse", "browse"
    if any(k in text for k in ("回答", "answer", "publish")):
        return "zhihu_answer", "create_answer"
    if any(k in text for k in ("文章", "article", "专栏")):
        return "zhihu_article", "create_article"
    if any(k in text for k in ("想法", "pin")):
        return "zhihu_pin", "create_pin"
    if any(k in text for k in ("提问", "question")):
        return "zhihu_question", "create_question"
    if typ:
        return "zhihu_activity", typ.lower()
    return None


def activity_entry_from_item(item: dict[str, Any], *, via: str = "api") -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    classified = classify_activity(item)
    if not classified:
        return None
    _event_type, event_kind = classified
    target = item.get("target") or {}
    content_url = _zhihu_content_url(target, item)
    if not content_url or not content_url.startswith("http"):
        actor = item.get("actor") or {}
        content_url = _zhihu_content_url(actor, item)
    if not content_url or not content_url.startswith("http"):
        if event_kind == "follow":
            for member in (target, item.get("actor") or {}):
                if isinstance(member, dict):
                    content_url = _zhihu_people_url(member)
                    if content_url:
                        break
        if not content_url or not content_url.startswith("http"):
            return None
    question = target.get("question") or {}
    title = (
        question.get("title")
        or target.get("title")
        or item.get("title")
        or str(item.get("verb") or "")
    )
    return {
        "source": "zhihu",
        "title": title,
        "url": content_url,
        "event_kind": event_kind,
        "verb": str(item.get("verb") or ""),
        "activity_type": str(item.get("type") or ""),
        "via": via,
    }
