"""Cookie 同步模块测试 / Cookie sync tests."""

import json

from osint_toolkit.auth.cookie_sync import (
    _group_cookies_by_domain,
    _to_cookie_header,
    load_cookie_header,
    sync_browser_cookies,
    validate_domain_cookie,
)


def test_group_cookies_by_domain():
    cookies = [
        {"name": "SESSDATA", "value": "abc", "domain": ".bilibili.com"},
        {"name": "z_c0", "value": "xyz", "domain": ".zhihu.com"},
    ]
    grouped = _group_cookies_by_domain(cookies, ["bilibili.com", "zhihu.com"])
    assert len(grouped["bilibili.com"]) == 1
    assert len(grouped["zhihu.com"]) == 1


def test_to_cookie_header_deduplicates_names():
    cookies = [
        {"name": "a", "value": "1", "domain": ".example.com"},
        {"name": "a", "value": "2", "domain": ".example.com"},
        {"name": "b", "value": "3", "domain": ".example.com"},
    ]
    header = _to_cookie_header(cookies)
    assert header == "a=1; b=3"


def test_validate_domain_cookie_missing_file(tmp_path):
    result = validate_domain_cookie("bilibili.com", tmp_path)
    assert result["ok"] is False


def test_validate_domain_cookie_with_sessdata(tmp_path):
    payload = {
        "domain": "bilibili.com",
        "cookie_header": "SESSDATA=abc; bili_jct=def",
        "cookies": [],
    }
    path = tmp_path / "bilibili.com.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = validate_domain_cookie("bilibili.com", tmp_path)
    assert result["ok"] is True
    assert load_cookie_header("bilibili.com", tmp_path) == "SESSDATA=abc; bili_jct=def"


def test_sync_browser_cookies_handles_missing_browser(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "osint_toolkit.auth.cookie_sync._extract_browser_cookies",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("can't find cookies file")),
    )
    result = sync_browser_cookies(browser="edge", domains=["bilibili.com"], output_dir=tmp_path)
    assert result.errors
    assert (tmp_path / "_index.json").exists()
