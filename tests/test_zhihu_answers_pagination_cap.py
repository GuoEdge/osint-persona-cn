"""Guard: zhihu _fetch_answers_sorted has a ceiling (A8)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from osint_toolkit.collectors.zhihu import ZhihuCollector


class FakeZhihuClient:
    def __init__(self):
        self.call_count = 0

    async def get(self, url, **_kw):
        self.call_count += 1
        return AsyncMock(
            status_code=200,
            json=lambda: {
                "data": [
                    {
                        "answer_id": i,
                        "content": "deadloop answer",
                        "voteup_count": 1,
                        "url": f"https://www.zhihu.com/question/1/answer/{i}",
                    }
                    for i in range(20)
                ],
                "paging": {
                    "is_end": False,
                    "next": f"https://www.zhihu.com/api/v4/questions/1/answers?limit=20&offset={self.call_count * 20}",
                },
            },
        )

    async def aclose(self):
        pass


@pytest.mark.asyncio
async def test_fetch_answers_sorted_has_cap():
    fake = FakeZhihuClient()
    collector = ZhihuCollector(client=fake)
    items = await collector._fetch_answers_sorted(
        qid="1",
        limit=200,
        sort_by="created",
    )
    assert fake.call_count <= 12, f"Too many API calls: {fake.call_count}"
    assert len(items) <= 200
