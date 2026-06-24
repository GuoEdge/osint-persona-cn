"""Guard: AI empty output / missing key fallback (B1-B6)."""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

import pytest

from osint_toolkit.ai.summarize import summarize_item, summarize_batch
from osint_toolkit.models.intel_item import IntelItem


def test_summarize_item_empty_output_falls_back():
    item = IntelItem(source="test", type="article", url="https://a.test/1", title="Test", content="Some real content here for fallback")
    with patch("osint_toolkit.ai.summarize.DeepSeekClient") as mk:
        inst = mk.return_value
        inst.chat = MagicMock(return_value="")
        summarize_item(item, client=None)
    assert item.summary
    assert len(item.summary.strip()) > 10
    assert "Some real content" in item.summary or "Test" in item.summary


def test_summarize_item_whitespace_output_falls_back():
    item = IntelItem(source="test", type="article", url="https://a.test/2", title="Whitespace", content="Real content for whitespace fallback")
    with patch("osint_toolkit.ai.summarize.DeepSeekClient") as mk:
        inst = mk.return_value
        inst.chat = MagicMock(return_value="   ")
        summarize_item(item, client=None)
    assert item.summary
    assert len(item.summary.strip()) > 10


def test_summarize_batch_no_key_does_not_crash():
    items = [IntelItem(source="test", type="article", url=f"https://a.test/{i}", title=f"T{i}", content="x") for i in range(3)]
    with patch("osint_toolkit.ai.summarize.DeepSeekClient", side_effect=ValueError("no key")):
        result = summarize_batch(items)
    assert len(result) == 3
    for item in result:
        assert item["summary"]


def test_generate_ai_daily_digest_no_key_falls_back():
    from osint_toolkit.ai.digest import generate_ai_daily_digest

    with (
        patch("osint_toolkit.ai.digest.DeepSeekClient", side_effect=ValueError("no key")),
        patch("osint_toolkit.ai.digest._today_events", return_value=[]),
        patch("osint_toolkit.ai.digest._today_intel", return_value=[]),
    ):
        result = generate_ai_daily_digest()
    assert isinstance(result, str)
    assert len(result) > 0


def test_suggest_queries_no_key_falls_back():
    from osint_toolkit.ai.suggest_queries import suggest_queries

    @dataclass
    class FakeCtx:
        recent_topics: tuple[str, ...] = ("topic1",)
        aliases: tuple[str, ...] = ()
        source_prefs: dict | None = None
        entity_names: tuple[str, ...] = ()
        search_persona_summary: str = ""
        persona_id: str = ""
        interest_hints: list[dict] = field(default_factory=list)

    ctx = FakeCtx(interest_hints=[{"title": "AI news", "url": "https://a.test"}])
    with patch("osint_toolkit.ai.suggest_queries.DeepSeekClient", side_effect=ValueError("no key")):
        result = suggest_queries(ctx, limit=5)
    assert isinstance(result, list)
    assert len(result) > 0
