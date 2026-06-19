"""composer / AI 产品查询不应误启音乐信源。"""

from __future__ import annotations

from osint_toolkit.ai.query_analyze import analyze_query
from osint_toolkit.ai.query_expand import expand_query
from osint_toolkit.collectors.source_resolve import resolve_search_sources
from osint_toolkit.collectors.source_routing import (
    _music_title_heuristic,
    compute_source_scores,
    is_music_intent,
    match_domain_route,
)


def test_composer_query_not_music_intent():
    for q in ("composer2.5 能力", "composer 能力", "Composer2.5 capabilities"):
        assert not is_music_intent(q), q
        assert not _music_title_heuristic(q), q


def test_composer_matches_dev_tech_route():
    route = match_domain_route("composer2.5 能力")
    assert route is not None
    assert route["id"] == "dev_tech"


def test_no_ai_analyze_does_not_recommend_entire_user_pool():
    sources = ["bilibili", "web", "zhihu", "netease_music", "qq_music"]
    result = analyze_query("composer2.5 能力", sources, no_ai=True)
    assert result["recommended_sources"] == []


def test_gentle_skips_music_for_composer_capability():
    sources = ["bilibili", "web", "zhihu", "netease_music", "qq_music", "weixin"]
    result = resolve_search_sources("composer2.5 能力", sources, mode="gentle")
    assert "netease_music" in result["skipped"]
    assert "qq_music" in result["skipped"]
    assert "bilibili" in result["active_sources"] or "github" in result["active_sources"] or "web" in result["active_sources"]


def test_expand_query_no_ai_skips_music_streaming():
    sources = ["bilibili", "web", "zhihu", "netease_music", "qq_music", "weixin"]
    expanded = expand_query("composer2.5 能力", sources, no_ai=True)
    active = expanded["active_sources"]
    assert "netease_music" not in active
    assert "qq_music" not in active


def test_opencode_not_music_intent_or_route():
    assert not is_music_intent("opencode")
    assert not _music_title_heuristic("opencode")
    route = match_domain_route("opencode")
    assert route is not None
    assert route["id"] == "dev_tech"


def test_music_streaming_only_when_user_selected():
    sources = ["bilibili", "web", "zhihu", "weixin"]
    result = resolve_search_sources("周杰伦 新歌 歌词", sources, mode="gentle")
    assert "netease_music" not in result["active_sources"]
    assert "qq_music" not in result["active_sources"]
    assert "netease_music" not in result["auto_enabled"]


def test_music_streaming_active_when_user_checked():
    sources = ["bilibili", "web", "zhihu", "netease_music", "qq_music"]
    result = resolve_search_sources("周杰伦 新歌", sources, mode="gentle")
    assert "netease_music" in result["active_sources"]
    assert "qq_music" in result["active_sources"]
    assert "netease_music" not in result["auto_enabled"]
    assert "qq_music" not in result["auto_enabled"]


def test_standalone_composer_not_song_title():
    assert not _music_title_heuristic("composer")
    scores = compute_source_scores("composer")
    assert scores["netease_music"] < 20


def test_song_title_still_detects_clear_music():
    assert is_music_intent("周杰伦 新歌 歌词")
    assert _music_title_heuristic("晴天")
