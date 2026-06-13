"""Subtitle track selection tests."""

from osint_toolkit.processors.subtitle import pick_subtitle_track


def test_pick_subtitle_prefers_ai_chinese():
    tracks = [
        {"lan": "en", "lan_doc": "English", "subtitle_url": "https://example.com/en"},
        {"lan": "zh-CN", "lan_doc": "中文（自动生成）", "subtitle_url": "https://example.com/ai"},
        {"lan": "zh-CN", "lan_doc": "中文", "subtitle_url": "https://example.com/cc"},
    ]
    picked = pick_subtitle_track(tracks)
    assert picked is not None
    assert "自动" in picked.get("lan_doc", "")


def test_pick_subtitle_falls_back_to_first():
    tracks = [{"lan": "ja", "lan_doc": "日本語", "subtitle_url": "https://example.com/ja"}]
    picked = pick_subtitle_track(tracks)
    assert picked == tracks[0]
