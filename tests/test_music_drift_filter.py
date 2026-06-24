"""Filter music drift expansions for tech/product queries."""

from __future__ import annotations

from osint_toolkit.ai.alias_filter import filter_relevant_terms, is_music_drift_term, is_valid_search_term


def test_music_drift_terms_rejected_for_composer_query():
    q = "composer2.5 能力"
    assert is_music_drift_term("composer2.5 音乐生成", q)
    assert is_music_drift_term("composer 2.5 AI作曲 评价", q)
    filtered = filter_relevant_terms(
        [q, "composer 2.5 功能评测", "composer2.5 音乐生成", "composer2.5 使用教程"],
        q,
    )
    assert "composer2.5 音乐生成" not in filtered
    assert "composer 2.5 功能评测" in filtered


def test_music_terms_kept_for_real_music_query():
    q = "周杰伦 新歌"
    assert not is_music_drift_term("晴天 歌词", q)
    assert is_valid_search_term("周杰伦 新歌 歌词", query=q, require_relevance=True)


def test_short_music_tokens_not_substring_matched_for_tech_query():
    q = "glm5.2 能力"
    assert not is_music_drift_term("postgresql 性能优化", q)
    assert not is_music_drift_term("mvvm 架构实践", q)
    assert is_music_drift_term("ost 原声带", q)
    assert is_music_drift_term("mv 推荐", q)
