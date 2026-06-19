"""Ask service context tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from osint_toolkit.services.ask import ask_question


def test_ask_without_run_includes_behavior(monkeypatch):
    captured = {}

    class FakeClient:
        def chat(self, *, messages):
            captured["messages"] = messages
            return "answer"

    monkeypatch.setattr("osint_toolkit.services.ask.maybe_load_persona_context", lambda: None)
    monkeypatch.setattr(
        "osint_toolkit.services.ask.load_ranked_behavior_samples",
        lambda **_: [{"title": "B站视频", "event_type": "bilibili_like"}],
    )
    monkeypatch.setattr("osint_toolkit.services.ask.knowledge.recall", lambda *a, **k: [])
    monkeypatch.setattr("osint_toolkit.services.ask.DeepSeekClient", lambda: FakeClient())

    result = ask_question("我最近关注什么？")
    assert result["answer"] == "answer"
    user_content = captured["messages"][1]["content"]
    assert "behavior_samples" in user_content


def test_ask_with_history_sends_prior_turns(monkeypatch):
    captured = {}

    class FakeClient:
        def chat(self, *, messages):
            captured["messages"] = messages
            return "follow-up answer"

    monkeypatch.setattr("osint_toolkit.services.ask.maybe_load_persona_context", lambda: None)
    monkeypatch.setattr("osint_toolkit.services.ask.load_ranked_behavior_samples", lambda **_: [])
    monkeypatch.setattr("osint_toolkit.services.ask.knowledge.recall", lambda *a, **k: [])
    monkeypatch.setattr("osint_toolkit.services.ask.DeepSeekClient", lambda: FakeClient())

    result = ask_question(
        "那知乎呢？",
        history=[{"question": "B站有什么？", "answer": "有几条视频"}],
    )
    assert result["answer"] == "follow-up answer"
    roles = [m["role"] for m in captured["messages"]]
    assert roles.count("user") == 2
    assert roles.count("assistant") == 1
