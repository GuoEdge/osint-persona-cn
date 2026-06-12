"""Persona simulation tests."""

from unittest.mock import MagicMock

from osint_toolkit.ai.persona_sim import simulate_items
from osint_toolkit.models.intel_item import IntelItem


def test_simulate_items_parses_json_array(monkeypatch):
    item = IntelItem(source="web", type="article", url="https://x", title="t", summary="s")
    client = MagicMock()
    client.chat.return_value = '[{"item_id":"' + item.id + '","interest":"interested","confidence":0.8,"verdict":"会看","reason":"相关"}]'
    monkeypatch.setattr("osint_toolkit.ai.persona_sim.load_persona_brief", lambda: "喜欢技术")
    out = simulate_items([item], client=client, no_ai=False, no_simulate=False)
    assert len(out) == 1
    assert out[0]["item_id"] == item.id
    assert out[0]["interest"] == "interested"
