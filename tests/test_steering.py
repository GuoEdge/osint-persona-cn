"""AI steering 测试."""

from osint_toolkit.ai.steering import build_system_prompt, is_step_enabled, load_directives


def test_load_directives_defaults():
    d = load_directives()
    assert "hard_constraints" in d
    assert d["enabled_steps"]["summarize"] is True


def test_is_step_disabled():
    assert is_step_enabled("summarize", no_ai=True) is False


def test_build_system_prompt_contains_constraints():
    prompt = build_system_prompt(task="摘要")
    assert "硬约束" in prompt
