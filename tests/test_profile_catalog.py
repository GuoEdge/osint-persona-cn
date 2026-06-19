"""Search profile catalog tests."""

from __future__ import annotations

from osint_toolkit.collectors.profile_catalog import get_search_profile, get_search_profile_catalog


def test_profile_catalog_has_builtin_modes():
    catalog = get_search_profile_catalog()
    ids = {p["id"] for p in catalog}
    assert "default" in ids
    assert "full" in ids
    assert "research" in ids
    assert "zhihu_deep" in ids


def test_default_profile_sources_and_copy():
    prof = get_search_profile("default")
    assert prof is not None
    assert prof["label"] == "默认"
    assert "zhihu" in prof["sources"]
    assert "weixin" in prof["sources"]
    assert prof["summary"]
    assert prof["detail"]


def test_research_profile_simulate_persona():
    prof = get_search_profile("research")
    assert prof is not None
    assert prof.get("simulate_persona") is True
    assert "weixin" not in prof["sources"]
