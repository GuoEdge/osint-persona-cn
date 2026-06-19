"""Dedup tests."""

from osint_toolkit.analyzers.dedup import dedup_items
from osint_toolkit.models.intel_item import IntelItem, IntelSignals


def test_dedup_by_url_and_similar_title():
    items = [
        IntelItem(source="web", type="snippet", url="https://a.com/1", title="丰川祥子 角色解析", content="x"),
        IntelItem(source="web", type="snippet", url="https://b.com/2", title="【丰川祥子】角色解析", content="y"),
        IntelItem(source="web", type="snippet", url="https://c.com/3", title="完全不同", content="z"),
    ]
    items[0].signals = IntelSignals(relevance=0.8)
    items[1].signals = IntelSignals(relevance=0.5)
    out = dedup_items(items)
    assert len(out) == 2
    assert out[0].url == "https://a.com/1"


def test_dedup_keeps_multiple_zhihu_answers_same_title():
    title = "如何评价最新发布并开源的 GLM-5.2？"
    items = [
        IntelItem(
            source="zhihu",
            type="answer",
            url="https://www.zhihu.com/question/1/answer/101",
            title=title,
            content="高赞观点 A",
        ),
        IntelItem(
            source="zhihu",
            type="answer",
            url="https://www.zhihu.com/question/1/answer/102",
            title=title,
            content="高赞观点 B",
        ),
        IntelItem(
            source="zhihu",
            type="answer",
            url="https://www.zhihu.com/question/1/answer/103",
            title=title,
            content="最新观点 C",
        ),
    ]
    out = dedup_items(items)
    assert len(out) == 3
