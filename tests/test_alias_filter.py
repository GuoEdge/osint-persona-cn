"""Alias filter tests."""

from osint_toolkit.ai.alias_filter import is_valid_search_term


def test_rejects_url_crumbs():
    assert not is_valid_search_term("zhihu.comhttps:", query="MCP")
    assert not is_valid_search_term("baidu.comhttps:", query="test")
    assert not is_valid_search_term("https:", query="MCP")


def test_rejects_long_questions():
    assert not is_valid_search_term("丰川祥子适合跟谁结婚？", query="丰川祥子")


def test_accepts_normal_aliases():
    assert is_valid_search_term("祥子", query="丰川祥子")
    assert is_valid_search_term("LLM", query="MCP")
