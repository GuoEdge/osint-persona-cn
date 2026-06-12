"""Ingest capability matrix for UI."""

from __future__ import annotations

from typing import Any

CAPABILITIES: list[dict[str, Any]] = [
    {"platform": "browser", "behavior": "浏览历史", "status": "supported", "note": "Edge 本地 SQLite"},
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
        "note": "每 4h 自动打开 B站/知乎同步页；点赞/赞同/收藏分页",
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
        "note": "AICU（需 probe PASS）；否则 space 页 + reply API 补洞",
    },
    {
        "platform": "bilibili",
        "behavior": "评论点赞",
        "status": "partial",
        "note": "仅扩展拦截 reply/action 增量，无历史列表",
    },
    {"platform": "zhihu", "behavior": "收藏夹", "status": "supported", "note": "API + 扩展"},
    {
        "platform": "zhihu",
        "behavior": "主页动态（赞/藏/关注/发布）",
        "status": "partial",
        "note": "activities API + browser-sync / 扩展补洞",
    },
    {
        "platform": "zhihu",
        "behavior": "最近浏览 recent-viewed",
        "status": "partial",
        "note": "browser-sync 打开 recent-viewed 拦截 API",
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
