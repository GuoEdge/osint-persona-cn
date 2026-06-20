"""Ingest capability matrix for UI."""

from __future__ import annotations

from typing import Any

CAPABILITIES: list[dict[str, Any]] = [
    {"platform": "browser", "behavior": "浏览历史", "status": "supported", "note": "Edge SQLite；完整同步默认导入最近 90 天，参与画像"},
    {
        "platform": "extension",
        "behavior": "被动浏览 + 停留",
        "status": "supported",
        "note": "B站/知乎/GitHub/V2EX/掘金等 12+ 平台，日常上网自动记",
    },
    {
        "platform": "extension",
        "behavior": "API 拦截 + 定时后台同步",
        "status": "supported",
        "note": "每 4h 自动打开 B 站补洞页；知乎赞同/浏览改由扩展被动采集（见 docs/ZHIHU_PERSONA.md）",
    },
    {
        "platform": "extension",
        "behavior": "右键收录知识库",
        "status": "supported",
        "note": "写 events 队列，上传后服务端 save_url 进知识库",
    },
    {
        "platform": "extension",
        "behavior": "高停留自动收录",
        "status": "supported",
        "note": "内容页停留 ≥90 秒自动进知识库（可配置 dwell_save_ms）",
    },
    {"platform": "bilibili", "behavior": "观看历史", "status": "supported", "note": "API 分页最多 500 条"},
    {"platform": "bilibili", "behavior": "收藏夹", "status": "supported", "note": "API + 扩展拦截"},
    {
        "platform": "bilibili",
        "behavior": "视频点赞",
        "status": "supported",
        "note": "WBI like/archive/list 分页 + browser-sync / 扩展补洞",
    },
    {
        "platform": "bilibili",
        "behavior": "关注列表",
        "status": "supported",
        "note": "x/relation/followings，随服务端拉取自动导入",
    },
    {
        "platform": "bilibili",
        "behavior": "发过评论",
        "status": "partial",
        "note": "AICU 批量 + 扩展拦截 reply/add 增量；服务端直连常被 WAF 拦截",
    },
    {
        "platform": "bilibili",
        "behavior": "评论点赞",
        "status": "partial",
        "note": "扩展拦截 reply/action 增量，无历史列表",
    },
    {
        "platform": "weixin",
        "behavior": "搜狗微信公众平台文章检索",
        "status": "supported",
        "note": "仅搜罗源（搜狗微信公众平台的公众号检索），无行为导入；见 search.weixin 配置",
    },
    {
        "platform": "bilibili",
        "behavior": "视频字幕/弹幕",
        "status": "supported",
        "note": "SDK get_subtitle/get_danmakus；搜索挖掘与 save 时填充 layers",
    },
    {"platform": "zhihu", "behavior": "收藏夹", "status": "supported", "note": "Cookie API + 扩展"},
    {
        "platform": "zhihu",
        "behavior": "我发布的回答/文章/想法",
        "status": "supported",
        "note": "members/{token}/answers|articles|pins",
    },
    {
        "platform": "zhihu",
        "behavior": "关注的人",
        "status": "supported",
        "note": "followees API",
    },
    {
        "platform": "zhihu",
        "behavior": "行为时间线（合成）",
        "status": "partial",
        "note": "由收藏/关注/发布合成；官方 activities 流已停用",
    },
    {
        "platform": "zhihu",
        "behavior": "赞同回答",
        "status": "partial",
        "note": "仅扩展 XHR 被动采集；voteanswers API 已 404",
    },
    {
        "platform": "zhihu",
        "behavior": "浏览记录",
        "status": "partial",
        "note": "Cookie 同步仅 Edge 知乎 URL；日常浏览请用扩展 page_visit",
    },
    {
        "platform": "browser",
        "behavior": "Playwright Edge 会话补洞",
        "status": "supported",
        "note": "Persistent 需关 Edge；CDP 模式可保持 Edge 开调试端口",
    },
    {"platform": "github", "behavior": "浏览/Star", "status": "partial", "note": "扩展记录访问与 GraphQL"},
    {"platform": "v2ex", "behavior": "浏览帖子", "status": "supported", "note": "扩展被动记录"},
    {"platform": "juejin", "behavior": "浏览文章", "status": "supported", "note": "扩展被动记录"},
]


def get_capabilities() -> dict[str, Any]:
    return {"items": CAPABILITIES}
