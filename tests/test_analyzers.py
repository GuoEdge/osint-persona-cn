"""分析器测试."""

from osint_toolkit.analyzers.dedup import dedup_items
from osint_toolkit.analyzers.engagement import engagement_sincerity
from osint_toolkit.analyzers.signals import extract_signals
from osint_toolkit.models.intel_item import IntelItem


def test_dedup_items():
    a = IntelItem(source="zhihu", type="answer", url="https://x.com/1", title="Same")
    b = IntelItem(source="zhihu", type="answer", url="https://x.com/1", title="Same")
    assert len(dedup_items([a, b])) == 1


def test_extract_signals():
    item = IntelItem(
        source="zhihu",
        type="answer",
        url="https://x.com/1",
        title="MCP 协议分析",
        content="这是一篇关于 MCP 协议的长文" * 20,
    )
    signals = extract_signals(item, "MCP")
    assert signals.relevance > 0


def test_engagement_sincerity():
    result = engagement_sincerity(duration_sec=3600, progress=0.8, entry="search")
    assert result["engagement_sincerity"] == "serious"
