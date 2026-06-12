"""Cookie to Playwright conversion tests."""

from osint_toolkit.auth.cookie_sync import cookies_for_playwright


def test_cookies_from_header_string(tmp_path, monkeypatch):
    cookies_dir = tmp_path / "cookies"
    cookies_dir.mkdir()
    (cookies_dir / "zhihu.com.json").write_text(
        '{"domain":"zhihu.com","cookie_header":"z_c0=abc; _zap=1"}',
        encoding="utf-8",
    )
    monkeypatch.setattr("osint_toolkit.auth.cookie_sync.get_cookies_dir", lambda: cookies_dir)
    items = cookies_for_playwright(["zhihu.com"])
    assert len(items) == 2
    assert items[0]["name"] == "z_c0"
