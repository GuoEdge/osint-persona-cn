"""Digest hot list integration tests."""

from __future__ import annotations

from osint_toolkit.exporters import digest as digest_mod


def test_daily_digest_includes_hot_list_section(monkeypatch, tmp_path):
    from osint_toolkit.models.intel_item import IntelItem
    from osint_toolkit.storage import sqlite as sqlite_mod

    monkeypatch.setattr(sqlite_mod, "get_db_path", lambda: tmp_path / "knowledge.db")
    monkeypatch.setattr(digest_mod, "get_data_dir", lambda: tmp_path)

    async def fake_hot_list(*, limit=15, client=None):
        return [
            IntelItem(
                source="zhihu",
                type="question",
                url="https://www.zhihu.com/question/99",
                title="今日热点",
                content="",
                personal={"hot_list": True},
            )
        ]

    monkeypatch.setattr(
        "osint_toolkit.ingest.zhihu_openapi.openapi_enabled",
        lambda feature: feature == "hot_list",
    )
    monkeypatch.setattr(
        "osint_toolkit.ingest.zhihu_openapi.hot_list",
        fake_hot_list,
    )

    text = digest_mod.generate_daily_digest(include_hot_list=True)
    assert "## 知乎热榜" in text
    assert "今日热点" in text
