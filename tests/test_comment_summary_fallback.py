"""Comment summary fallback tests."""

import pytest

from osint_toolkit.analyzers.comments import summarize_comments


class FakeClient:
    def __init__(self, text: str) -> None:
        self.text = text

    def chat(self, messages):
        return self.text


@pytest.mark.asyncio
async def test_summarize_comments_too_short_ai_output_falls_back():
    comments = [{"content": "真实评论内容很关键", "likes": 5}]

    result = await summarize_comments(comments, client=FakeClient("OK"))

    assert result.startswith("社区评论精选:")
    assert "真实评论内容很关键" in result
    assert result != "OK"
