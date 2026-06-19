"""领域信源路由测试."""

from osint_toolkit.collectors.registry import merge_source_priority
from osint_toolkit.collectors.source_routing import apply_source_routing, match_domain_route


def test_merge_source_priority_keeps_all_user_sources():
    merged = merge_source_priority(
        ["zhihu", "bilibili", "web"],
        ["ithome", "web", "zhihu"],
    )
    assert set(merged) == {"zhihu", "bilibili", "web"}
    assert merged[0] == "ithome" or merged.index("bilibili") >= 0


def test_match_music_route_by_keyword():
    route = match_domain_route("周杰伦 新歌 歌词")
    assert route is not None
    assert route["id"] == "music"


def test_apply_routing_does_not_auto_enable_music_sources():
    result = apply_source_routing("晴天", ["zhihu", "bilibili", "web"], None)
    assert "bilibili" in result["active_sources"]
    assert "netease_music" not in result["auto_enabled"]
    assert "netease_music" not in result["active_sources"]


def test_apply_routing_glm_enables_github():
    result = apply_source_routing(
        "如何评价开源 GLM-5.2",
        ["zhihu", "bilibili", "web", "weixin"],
        None,
    )
    assert result["domain"] == "dev_tech"
    assert "github" in result["active_sources"]
    assert "weixin" in result["skipped"]


def test_match_gaming_route():
    route = match_domain_route("PS5 独占游戏 机核")
    assert route is not None
    assert route["id"] == "gaming"


def test_apply_routing_social_auto_enables_weibo():
    result = apply_source_routing("微博热搜 吃瓜", ["zhihu", "web"], None)
    assert result["domain"] == "social_opinion"
    assert "weibo" in result["active_sources"]


def test_apply_routing_off_mode_via_resolve():
    result = apply_source_routing(
        "笔记本显卡评测",
        ["zhihu", "web", "ithome"],
        ["zhihu", "web"],
        profile="default",
    )
    assert "ithome" in result["active_sources"]
