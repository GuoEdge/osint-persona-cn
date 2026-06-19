"""信源身份与 Cookie 策略 / Per-source authentication policy."""

from __future__ import annotations

from typing import Any

# mode:
# - none: 无需登录
# - cookie_required: 必须同步 Cookie，否则跳过该信源
# - cookie_recommended: 建议 Cookie；无则 SERP 兜底并提示
# - cookie_or_api: Cookie 或 API Key 二选一
# - serp_only: 仅搜索引擎 site: 摘要（不尝试登录态页面抓取）

SOURCE_AUTH: dict[str, dict[str, Any]] = {
    "zhihu": {
        "mode": "cookie_or_api",
        "cookie_domains": ["zhihu.com"],
        "api_key": "zhihu_openapi",
        "login_url": "https://www.zhihu.com",
        "login_hint": "在浏览器登录知乎后，用扩展「同步 Cookie」；或配置知乎开放平台 Key",
        "serp_fallback": False,
    },
    "bilibili": {
        "mode": "cookie_required",
        "cookie_domains": ["bilibili.com"],
        "login_url": "https://www.bilibili.com",
        "login_hint": "在浏览器登录 B 站后，用扩展「从浏览器同步 Cookie」",
        "serp_fallback": False,
    },
    "weixin": {
        "mode": "cookie_recommended",
        "cookie_domains": ["weixin.sogou.com", "mp.weixin.qq.com"],
        "login_url": "https://mp.weixin.qq.com",
        "login_hint": "搜狗微信检索；登录微信公众平台并同步 Cookie 可提升成功率",
        "serp_fallback": True,
    },
    "web": {"mode": "none", "serp_fallback": True},
    "v2ex": {
        "mode": "cookie_recommended",
        "cookie_domains": ["v2ex.com"],
        "login_url": "https://www.v2ex.com",
        "login_hint": "公开帖可读；登录并同步 Cookie 可访问更多内容",
        "serp_fallback": True,
    },
    "weibo": {
        "mode": "cookie_recommended",
        "cookie_domains": ["weibo.com"],
        "login_url": "https://weibo.com",
        "login_hint": "建议登录微博并同步 Cookie；未登录时退化为搜索引擎 site: 摘要",
        "serp_fallback": True,
    },
    "xiaohongshu": {
        "mode": "cookie_recommended",
        "cookie_domains": ["xiaohongshu.com"],
        "login_url": "https://www.xiaohongshu.com",
        "login_hint": "建议登录小红书并同步 Cookie；未登录时退化为搜索引擎 site: 摘要",
        "serp_fallback": True,
    },
    "tieba": {
        "mode": "cookie_recommended",
        "cookie_domains": ["tieba.baidu.com"],
        "login_url": "https://tieba.baidu.com",
        "login_hint": "建议登录百度贴吧并同步 Cookie",
        "serp_fallback": True,
    },
    "jike": {
        "mode": "cookie_recommended",
        "cookie_domains": ["okjike.com"],
        "login_url": "https://web.okjike.com",
        "login_hint": "建议登录即刻并同步 Cookie",
        "serp_fallback": True,
    },
    "maimai": {
        "mode": "cookie_recommended",
        "cookie_domains": ["maimai.cn"],
        "login_url": "https://maimai.cn",
        "login_hint": "建议登录脉脉并同步 Cookie",
        "serp_fallback": True,
    },
    "github": {"mode": "none", "serp_fallback": True},
    "rss": {"mode": "none", "serp_fallback": False},
}

_MUSIC_SOURCES = frozenset({"netease_music", "qq_music", "kugou", "migu", "ximalaya"})

_MUSIC_AUTH = {
    "mode": "serp_only",
    "cookie_domains": [],
    "login_url": "",
    "login_hint": "默认仅用 Bing/百度等 site: 摘要，无需登录音乐 App；不抓取需登录的曲目页",
    "serp_fallback": True,
}

_SITE_DEFAULT_AUTH = {
    "mode": "serp_only",
    "cookie_domains": [],
    "login_url": "",
    "login_hint": "通过搜索引擎 site: 域名检索公开页面摘要",
    "serp_fallback": True,
}


def get_source_auth(source_id: str) -> dict[str, Any]:
    sid = str(source_id or "").strip()
    if sid in SOURCE_AUTH:
        return dict(SOURCE_AUTH[sid])
    if sid in _MUSIC_SOURCES:
        entry = dict(_MUSIC_AUTH)
        from osint_toolkit.collectors.source_catalog import get_source_entries

        for row in get_source_entries():
            if row.get("id") == sid and row.get("domain"):
                entry["cookie_domains"] = [str(row["domain"])]
                entry["login_url"] = f"https://{row['domain']}"
        return entry
    from osint_toolkit.collectors.registry import COLLECTORS

    if sid in COLLECTORS:
        return dict(_SITE_DEFAULT_AUTH)
    return {"mode": "none", "serp_fallback": False}


def auth_fields_for_catalog(source_id: str) -> dict[str, Any]:
    """供信源目录 / API 暴露的精简字段。"""
    policy = get_source_auth(source_id)
    mode = str(policy.get("mode") or "none")
    return {
        "auth_mode": mode,
        "cookie_domains": list(policy.get("cookie_domains") or []),
        "login_url": str(policy.get("login_url") or ""),
        "login_hint": str(policy.get("login_hint") or ""),
        "serp_fallback": bool(policy.get("serp_fallback")),
        "needs_cookie_sync": mode in {"cookie_required", "cookie_recommended", "cookie_or_api"},
    }
