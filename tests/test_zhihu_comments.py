"""Zhihu comment fetch tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from osint_toolkit.collectors.zhihu import ZhihuCollector


def test_fetch_comments_url_answer():
    col = ZhihuCollector()
    assert col._comment_resource("https://www.zhihu.com/question/1/answer/2") == ("answers", "2")


def test_fetch_comments_url_standalone_answer():
    col = ZhihuCollector()
    assert col._comment_resource("https://www.zhihu.com/answer/2") == ("answers", "2")


def test_fetch_comments_url_article():
    col = ZhihuCollector()
    assert col._comment_resource("https://zhuanlan.zhihu.com/p/12345") == ("articles", "12345")


@pytest.mark.asyncio
async def test_fetch_comments_uses_offset_from_next_url():
    col = ZhihuCollector(client=MagicMock())
    first = MagicMock()
    first.status_code = 200
    first.json.return_value = {
        "data": [{"id": "c1", "content": "一楼", "vote_count": 1}],
        "paging": {
            "is_end": False,
            "next": "https://www.zhihu.com/api/v4/comment_v5/answers/2/root_comment?order_by=score&limit=20&offset=20",
        },
    }
    second = MagicMock()
    second.status_code = 200
    second.json.return_value = {
        "data": [{"id": "c2", "content": "二楼", "vote_count": 2}],
        "paging": {"is_end": True},
    }
    col.client.get = AsyncMock(side_effect=[first, second])

    comments = await col._fetch_comments_by_order("answers", "2", "score", limit=5, max_pages=3)

    assert [c["id"] for c in comments] == ["c1", "c2"]
    assert "offset=20" in col.client.get.await_args_list[1].args[0]
    assert "offset=https%3A" not in col.client.get.await_args_list[1].args[0]
