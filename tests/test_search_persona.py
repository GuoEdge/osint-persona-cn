"""Search persona boost and ranking tests."""

from __future__ import annotations

from osint_toolkit.analyzers.signals import apply_persona_boost
from osint_toolkit.models.intel_item import IntelItem, IntelSignals


def test_apply_persona_boost():
    item = IntelItem(source="web", type="article", url="http://x", title="Python 异步教程", content="")
    item.signals = IntelSignals(relevance=0.5)
    apply_persona_boost(item, ["python", "异步"])
    assert item.signals.relevance > 0.5


def _rank_score(item, sim_map):
    sim = sim_map.get(item.id, {})

    def _sim_confidence(s):
        if s.get("interest") != "interested":
            return 0.0
        return float(s.get("confidence") or 0)

    return (
        item.signals.relevance
        + _sim_confidence(sim) * 0.3
        + (0.15 if item.personal.get("already_seen") else 0.0)
    )


def test_search_ranking_prefers_seen_and_sim():
    a = IntelItem(id="a", source="web", type="x", url="http://a", title="A", content="")
    b = IntelItem(id="b", source="web", type="x", url="http://b", title="B", content="")
    a.signals = IntelSignals(relevance=0.5)
    b.signals = IntelSignals(relevance=0.5)
    b.personal["already_seen"] = True
    sim_map = {"b": {"interest": "interested", "confidence": 0.9}}
    items = [a, b]
    items.sort(key=lambda i: _rank_score(i, sim_map), reverse=True)
    assert items[0].id == "b"
