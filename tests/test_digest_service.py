"""Digest service tests."""

from __future__ import annotations

from osint_toolkit.services import digest as digest_mod


def test_load_daily_digest(tmp_path, monkeypatch):
    digests_dir = tmp_path / "digests"
    digests_dir.mkdir()
    (digests_dir / "2026-06-14.md").write_text("# 今日简报\n测试内容", encoding="utf-8")
    monkeypatch.setattr(digest_mod, "get_data_dir", lambda: tmp_path)
    data = digest_mod.load_daily_digest("2026-06-14")
    assert "测试内容" in data["content"]
    assert data["date"] == "2026-06-14"
