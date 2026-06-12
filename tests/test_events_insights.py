"""Events insights cache tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from osint_toolkit.services import events_insights


def test_insights_cache_hit(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    cache_file = cache_dir / "behavior_insights.json"
    cache_file.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "insights": "cached text",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(events_insights, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(events_insights, "_cache_path", lambda: cache_file)

    result = events_insights.get_behavior_insights(refresh=False, no_ai=True)
    assert result["cached"] is True
    assert result["insights"] == "cached text"


def test_insights_cache_expired(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    cache_file = cache_dir / "behavior_insights.json"
    old = datetime.now(UTC) - timedelta(hours=2)
    cache_file.write_text(
        json.dumps({"generated_at": old.isoformat(), "insights": "old"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(events_insights, "get_data_dir", lambda: tmp_path)
    monkeypatch.setattr(events_insights, "_cache_path", lambda: cache_file)
    monkeypatch.setattr(events_insights, "load_ranked_behavior_samples", lambda **_: [])
    monkeypatch.setattr(events_insights, "maybe_load_persona_context", lambda: None)

    result = events_insights.get_behavior_insights(refresh=False, no_ai=True)
    assert result["cached"] is False
