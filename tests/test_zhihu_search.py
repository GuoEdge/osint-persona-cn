"""Zhihu deep search tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from osint_toolkit.collectors.zhihu import ZhihuCollector
from osint_toolkit.models.intel_item import IntelItem


def test_parse_question_object():
    col = ZhihuCollector(client=MagicMock())
    item = col._parse_object(
        {
            "type": "question",
            "id": 12345,
            "title": "如何学习 Python？",
            "excerpt": "想系统入门",
            "comment_count": 88,
        }
    )
    assert item is not None
    assert item.type == "question"
    assert item.url == "https://www.zhihu.com/question/12345"
    assert item.title == "如何学习 Python？"


def test_question_id_from_ref_includes_answer_url():
    assert ZhihuCollector.question_id_from_ref("https://www.zhihu.com/question/99/answer/1") == "99"


@pytest.mark.asyncio
async def test_expand_questions_from_answer_hit(monkeypatch):
    cfg = {
        "zhihu_expand_answers": True,
        "zhihu_expand_from_answers": True,
        "zhihu_expand_question_top": 2,
        "zhihu_answers_per_question": 1,
    }
    monkeypatch.setattr("osint_toolkit.collectors.zhihu.get_search_config", lambda: cfg)
    client = MagicMock()

    async def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json = lambda: {
            "data": [
                {
                    "id": 501,
                    "question": {"id": 88, "title": "来自回答的提问"},
                    "content": "<p>展开</p>",
                    "voteup_count": 3,
                    "comment_count": 1,
                    "author": {"name": "U"},
                }
            ],
            "paging": {"is_end": True},
        }
        return resp

    client.get = AsyncMock(side_effect=fake_get)
    col = ZhihuCollector(client=client)
    seed = [
        IntelItem(
            source="zhihu",
            type="answer",
            url="https://www.zhihu.com/question/88/answer/9",
            title="命中回答",
            content="",
        )
    ]
    expanded = await col.expand_questions(seed)
    assert len(expanded) == 1
    assert expanded[0].personal["parent_question_title"] == "来自回答的提问"


@pytest.mark.asyncio
async def test_fetch_comments_attaches_child_replies(monkeypatch):
    cfg = {
        "zhihu_comment_limit": 5,
        "zhihu_comment_pages": 1,
        "zhihu_fetch_child_comments": True,
        "zhihu_child_comment_roots": 1,
        "zhihu_child_comment_limit": 2,
    }
    monkeypatch.setattr("osint_toolkit.collectors.zhihu.get_search_config", lambda: cfg)
    client = MagicMock()

    async def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        if "child_comment" in url:
            resp.json = lambda: {
                "data": [{"id": "c2", "content": "子评", "vote_count": 1, "author": {"name": "B"}}],
                "paging": {"is_end": True},
            }
        else:
            resp.json = lambda: {
                "data": [
                    {
                        "id": "c1",
                        "content": "根评",
                        "vote_count": 9,
                        "child_comment_count": 1,
                        "author": {"name": "A"},
                    }
                ],
                "paging": {"is_end": True},
            }
        return resp

    client.get = AsyncMock(side_effect=fake_get)
    col = ZhihuCollector(client=client)
    comments = await col.fetch_comments("https://www.zhihu.com/question/1/answer/2")
    assert comments[0]["replies"][0]["content"] == "子评"


def test_per_query_limit_aggressive_floor(monkeypatch):
    monkeypatch.setattr(
        "osint_toolkit.ai.query_expand.get_search_config",
        lambda: {"zhihu_aggressive": True, "per_query_limit_ratio": 0.85, "zhihu_per_query_limit_min": 20},
    )
    from osint_toolkit.ai.query_expand import per_query_limit

    assert per_query_limit(10, 5) == 20


@pytest.mark.asyncio
async def test_fetch_question_answers_paginates():
    client = MagicMock()
    page1 = {
        "data": [
            {
                "id": 1,
                "question": {"id": 99, "title": "Q"},
                "content": "<p>回答一</p>",
                "voteup_count": 100,
                "comment_count": 5,
                "author": {"name": "A"},
            }
        ],
        "paging": {
            "is_end": False,
            "next": "https://www.zhihu.com/api/v4/questions/99/answers?offset=20&limit=20",
        },
    }
    page2 = {
        "data": [
            {
                "id": 2,
                "question": {"id": 99, "title": "Q"},
                "content": "<p>回答二</p>",
                "voteup_count": 50,
                "comment_count": 2,
                "author": {"name": "B"},
            }
        ],
        "paging": {"is_end": True},
    }

    async def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json = lambda: page2 if "offset=20" in url else page1
        return resp

    client.get = AsyncMock(side_effect=fake_get)
    col = ZhihuCollector(client=client)
    answers = await col.fetch_question_answers("https://www.zhihu.com/question/99", limit=5)
    assert len(answers) == 2
    assert answers[0].type == "answer"
    assert answers[0].url.endswith("/answer/1")


@pytest.mark.asyncio
async def test_search_merges_types_and_expands_questions(monkeypatch):
    cfg = {
        "zhihu_search_types": ["general", "content"],
        "zhihu_search_pages": 1,
        "zhihu_aggressive": False,
        "zhihu_expand_answers": True,
        "zhihu_expand_from_answers": False,
        "zhihu_expand_question_top": 1,
        "zhihu_answers_per_question": 2,
    }
    monkeypatch.setattr("osint_toolkit.collectors.zhihu.get_search_config", lambda: cfg)

    client = MagicMock()

    async def fake_get(url, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        if "search_v3" in url and "t=content" in url:
            resp.json = lambda: {
                "data": [
                    {
                        "object": {
                            "type": "question",
                            "id": 77,
                            "title": "测试提问",
                            "excerpt": "详情",
                        }
                    }
                ],
                "paging": {"is_end": True},
            }
        elif "search_v3" in url:
            resp.json = lambda: {
                "data": [
                    {
                        "object": {
                            "type": "answer",
                            "id": 9,
                            "question": {"id": 88, "title": "已有回答"},
                            "excerpt": "摘要",
                            "voteup_count": 1,
                            "comment_count": 0,
                            "author": {"name": "U"},
                        }
                    }
                ],
                "paging": {"is_end": True},
            }
        elif "questions/77/answers" in url:
            resp.json = lambda: {
                "data": [
                    {
                        "id": 701,
                        "question": {"id": 77, "title": "测试提问"},
                        "content": "<p>展开回答</p>",
                        "voteup_count": 9,
                        "comment_count": 3,
                        "author": {"name": "X"},
                    }
                ],
                "paging": {"is_end": True},
            }
        else:
            resp.status_code = 404
            resp.json = lambda: {}
        return resp

    client.get = AsyncMock(side_effect=fake_get)
    col = ZhihuCollector(client=client)
    items = await col.search("测试", limit=10)
    types = {i.type for i in items}
    assert "question" in types
    assert "answer" in types
    expanded = [i for i in items if i.personal.get("parent_question_url")]
    assert expanded
    assert expanded[0].personal["parent_question_title"] == "测试提问"


def test_comment_limits_from_config(monkeypatch):
    monkeypatch.setattr(
        "osint_toolkit.collectors.zhihu.get_search_config",
        lambda: {"zhihu_comment_limit": 80, "zhihu_comment_pages": 5},
    )
    col = ZhihuCollector(client=MagicMock())
    assert col._comment_limits() == (80, 5)
