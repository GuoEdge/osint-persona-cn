"""Alias filter tests."""

from osint_toolkit.ai.alias_filter import (
    filter_relevant_terms,
    has_relevance_to_query,
    is_narrow_product_query,
    is_valid_search_term,
    product_variants,
)


def test_rejects_url_crumbs():
    assert not is_valid_search_term("zhihu.comhttps:", query="MCP")
    assert not is_valid_search_term("baidu.comhttps:", query="test")
    assert not is_valid_search_term("https:", query="MCP")


def test_rejects_long_questions():
    assert not is_valid_search_term("丰川祥子适合跟谁结婚？", query="丰川祥子")


def test_accepts_normal_aliases():
    assert is_valid_search_term("祥子", query="丰川祥子")
    assert is_valid_search_term("LLM", query="MCP")


def test_narrow_product_query_detects_glm():
    assert is_narrow_product_query("glm5.2")
    assert is_narrow_product_query("glm 5.2")
    assert not is_narrow_product_query("丰川祥子")


def test_product_variants_for_glm():
    variants = product_variants("glm5.2")
    assert "GLM-5.2" in variants
    assert "GLM 5.2" in variants


def test_rejects_drift_terms_for_glm():
    query = "glm5.2"
    assert has_relevance_to_query("GLM-5.2", query)
    assert has_relevance_to_query("GLM5.2", query)
    assert not has_relevance_to_query("字幕:ai", query)
    assert not has_relevance_to_query("论文精读", query)
    assert not has_relevance_to_query("康奈尔笔记法", query)
    assert not has_relevance_to_query("5.2", query)


def test_filter_relevant_terms_drops_noise():
    query = "glm 5.2"
    kept = filter_relevant_terms(
        ["glm 5.2", "GLM-5.2", "字幕:ai", "论文精读", "新智元导读"],
        query,
    )
    assert "GLM-5.2" in kept
    assert "字幕:ai" not in kept
    assert "论文精读" not in kept
