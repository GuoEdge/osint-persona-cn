"""信源自动调度测试 / Source auto-route resolution tests."""

from osint_toolkit.collectors.source_resolve import resolve_search_sources
from osint_toolkit.collectors.source_routing import apply_source_routing, compute_source_scores, match_domain_route


def test_compute_scores_dev_tech_query():
    scores = compute_source_scores("如何评价开源 GLM-5.2")
    assert scores["github"] >= 45
    assert scores["juejin"] >= 45
    assert scores["weixin"] < 20


def test_gentle_auto_enables_github_for_glm():
    result = resolve_search_sources(
        "如何评价最新发布并开源的 GLM-5.2",
        ["zhihu", "bilibili", "web", "weixin"],
        profile="default",
        mode="gentle",
    )
    assert "github" in result["auto_enabled"]
    assert "github" in result["active_sources"]
    assert "weixin" in result["skipped"]


def test_gentle_skips_irrelevant_music_site_for_tech():
    result = resolve_search_sources(
        "GLM-5.2 开源 大模型",
        ["zhihu", "web", "netease_music", "kugou"],
        mode="gentle",
    )
    assert "netease_music" in result["skipped"]
    assert "kugou" in result["skipped"]


def test_off_mode_keeps_all_user_sources():
    result = resolve_search_sources(
        "GLM-5.2",
        ["zhihu", "weixin", "web"],
        mode="off",
    )
    assert set(result["active_sources"]) == {"zhihu", "weixin", "web"}
    assert result["auto_enabled"] == []


def test_zhihu_deep_profile_restricts_pool():
    result = resolve_search_sources(
        "周杰伦 新歌",
        ["zhihu", "bilibili", "web"],
        profile="zhihu_deep",
        mode="gentle",
    )
    assert result["active_sources"] == ["zhihu"]
    assert "bilibili" in result["skipped"]


def test_music_route_does_not_auto_enable_streaming_without_user_pick():
    result = apply_source_routing("晴天", ["zhihu", "bilibili", "web"], None)
    assert "netease_music" not in result["auto_enabled"]
    assert "netease_music" not in result["active_sources"]
    assert "bilibili" in result["active_sources"]


def test_music_route_uses_streaming_when_user_picked():
    result = apply_source_routing("晴天", ["zhihu", "bilibili", "netease_music", "web"], None)
    assert "netease_music" in result["active_sources"]
    assert "netease_music" not in result["auto_enabled"]


def test_match_music_route_requires_explicit_keywords():
    assert match_domain_route("晴天") is None
    route = match_domain_route("周杰伦 新歌 歌词")
    assert route is not None
    assert route["id"] == "music"
