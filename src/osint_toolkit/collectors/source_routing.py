"""按查询关键词推荐垂直信源 / Domain-aware source routing."""

from __future__ import annotations

import re
from typing import Any

from osint_toolkit.collectors.registry import COLLECTORS

_DOMAIN_ROUTES: list[dict[str, Any]] = [
    {
        "id": "music",
        "label": "音乐",
        "keywords": (
            "歌曲", "音乐", "单曲", "专辑", "歌手", "乐队", "歌词", "编曲", "作曲", "作词",
            "mv", "ost", "bgm", "翻唱", "live", "演唱会", "音源", "乐评", "playlist",
            "网易云", "qq音乐", "酷狗", "spotify", "melon",
        ),
        "sources": ["bilibili", "netease_music", "qq_music", "web", "zhihu", "douban", "kugou", "migu", "ximalaya"],
        "site_domains": ["music.163.com", "y.qq.com", "kugou.com", "music.migu.cn", "ximalaya.com"],
    },
    {
        "id": "tech_news",
        "label": "科技数码资讯",
        "keywords": (
            "手机", "笔记本", "平板", "显卡", "cpu", "芯片", "处理器", "发布会",
            "iphone", "安卓", "android", "windows", "macos", "ios", "鸿蒙",
            "小米", "华为", "苹果", "oppo", "vivo", "荣耀", "三星", "intel", "amd", "nvidia",
            "it之家", "数码", "评测", "固件", "系统更新", "ai手机", "智能手表",
        ),
        "sources": ["ithome", "sspai", "smzdm", "chiphell", "web", "zhihu", "bilibili", "weixin"],
        "site_domains": ["ithome.com", "sspai.com", "36kr.com", "smzdm.com", "chiphell.com"],
    },
    {
        "id": "dev_tech",
        "label": "开发与技术社区",
        "keywords": (
            "编程", "开源", "github", "docker", "kubernetes", "k8s", "python", "rust", "golang",
            "前端", "后端", "api", "框架", "数据库", "linux", "服务器", "devops", "mcp", "llm",
            "大模型", "开源模型", "glm", "智谱", "transformer", "推理", "微调", "agent",
            "v2ex", "程序员", "代码", "算法", "掘金",
            "composer", "cursor", "codex", "copilot", "claude", "gemini", "gpt", "deepseek",
            "opencode", "open code", "aider", "cline", "windsurf",
            "能力", "模型能力", "版本",
        ),
        "sources": ["v2ex", "juejin", "github", "hackernews", "reddit", "web", "zhihu", "bilibili"],
        "site_domains": ["github.com", "v2ex.com", "juejin.cn", "news.ycombinator.com", "reddit.com"],
    },
    {
        "id": "product_biz",
        "label": "产品商业观察",
        "keywords": (
            "融资", "上市", "财报", "商业模式", "saas", "创业", "估值", "并购", "战略",
            "36氪", "虎嗅", "商业", "市场分析", "行业报告",
        ),
        "sources": ["kr36", "huxiu", "caixin", "thepaper", "maimai", "web", "zhihu", "weixin", "ithome"],
        "site_domains": ["36kr.com", "huxiu.com", "caixin.com", "thepaper.cn", "maimai.cn"],
    },
    {
        "id": "acg_culture",
        "label": "ACG / 亚文化",
        "keywords": (
            "动漫", "番剧", "声优", "手办", "二次元", "galgame", "vtuber", "cos",
            "漫画", "动画", "角色", "同人",
        ),
        "sources": ["bilibili", "zhihu", "web", "douban", "nga", "gcores"],
        "site_domains": ["bilibili.com", "douban.com", "ngabbs.com", "gcores.com"],
    },
    {
        "id": "culture_review",
        "label": "书影音文化",
        "keywords": (
            "电影", "电视剧", "纪录片", "书籍", "读书", "影评", "评分", "豆瓣",
        ),
        "sources": ["douban", "zhihu", "web", "bilibili", "weixin", "ximalaya", "thepaper"],
        "site_domains": ["douban.com", "ximalaya.com", "thepaper.cn"],
    },
    {
        "id": "gaming",
        "label": "游戏",
        "keywords": (
            "游戏", "主机", "steam", "ps5", "switch", "xbox", "手游", "电竞", "单机",
            "机核", "gcores", "chiphell", "nga", "任天堂", "索尼", "育碧", "暴雪",
        ),
        "sources": ["nga", "gcores", "chiphell", "bilibili", "zhihu", "web"],
        "site_domains": ["ngabbs.com", "gcores.com", "chiphell.com"],
    },
    {
        "id": "social_opinion",
        "label": "社交舆情",
        "keywords": (
            "微博", "热搜", "吃瓜", "舆情", "小红书", "笔记", "即刻", "jike", "贴吧",
            "脉脉", "职场", "爆料", "小道消息", "瓜", "八卦",
        ),
        "sources": ["weibo", "xiaohongshu", "jike", "tieba", "maimai", "zhihu", "web"],
        "site_domains": ["weibo.com", "xiaohongshu.com", "okjike.com", "tieba.baidu.com", "maimai.cn"],
    },
]

_TECH_BLOCK = re.compile(
    r"手机|芯片|编程|代码|api|框架|服务器|windows|android|iphone|发布会|融资|财报|"
    r"composer|cursor|codex|claude|gemini|gpt|llm|mcp|agent|openai|anthropic|"
    r"opencode|open.?code|aider|cline|windsurf|copilot|"
    r"模型|能力|版本|开源|评测|agent|sdk|github|docker|devops",
    re.I,
)

_MUSIC_FALSE_POSITIVE = re.compile(
    r"composer|cursor|codex|claude|gemini|gpt|llm|mcp|agent|openai|anthropic|"
    r"copilot|sonnet|opus|glm|deepseek|opencode|open.?code|aider|cline|windsurf|"
    r"能力|模型|版本|编程|框架|docker|kubernetes|开源|评测|\d+\.\d+|"
    r"\bcode\b|github|sdk|api|dev",
    re.I,
)


def _music_title_heuristic(query: str) -> bool:
    """短查询且无技术/商业词时，疑似歌曲名（不用于自动启用音乐站）。"""
    q = query.strip()
    if len(q) < 2 or len(q) > 22:
        return False
    if _TECH_BLOCK.search(q) or _MUSIC_FALSE_POSITIVE.search(q):
        return False
    if re.search(r"[a-z]", q, re.I) and re.search(r"(code|open|dev|api|git|sdk|ai|llm)", q, re.I):
        return False
    if re.search(r"(歌|曲|music|mv|ost|bgm)", q, re.I):
        return True
    # 纯中文短标题，如「晴天」；含拉丁字母的短词更可能是产品名
    if re.fullmatch(r"[\u4e00-\u9fff·'\-\s]{2,12}", q):
        return True
    return False


def _explicit_music_keywords(query: str) -> bool:
    """查询中明确出现音乐领域词（非歌曲名猜测）。"""
    q = (query or "").strip().lower()
    if len(q) < 2:
        return False
    music_route = next((r for r in _DOMAIN_ROUTES if r["id"] == "music"), None)
    if not music_route:
        return False
    return any(kw.lower() in q for kw in music_route.get("keywords") or ())


def _music_source_ids() -> frozenset[str]:
    from osint_toolkit.collectors.source_catalog import get_source_entries

    return frozenset(str(e["id"]) for e in get_source_entries() if e.get("category") == "music")


def is_music_intent(query: str) -> bool:
    """是否明确为音乐/歌曲类话题（非 composer / opencode 等产品名误判）。"""
    if _explicit_music_keywords(query):
        return True
    return _music_title_heuristic(query)


def compute_source_scores(
    query: str,
    *,
    ai_priority: list[str] | None = None,
) -> dict[str, float]:
    """为每个信源计算 0–100 的话题相关度（多领域取最大）。"""
    scores: dict[str, float] = {sid: 0.0 for sid in COLLECTORS}
    q = (query or "").strip().lower()
    if len(q) < 2:
        return scores

    for route in _DOMAIN_ROUTES:
        kw_hits = sum(1 for kw in route["keywords"] if kw.lower() in q)
        if kw_hits == 0:
            continue
        route_weight = kw_hits * 12.0
        for i, sid in enumerate(route.get("sources") or []):
            if sid not in scores:
                continue
            pos_boost = max(8.0, 28.0 - i * 2.0)
            scores[sid] = max(scores[sid], route_weight + pos_boost)

    if _music_title_heuristic(query):
        music = next((r for r in _DOMAIN_ROUTES if r["id"] == "music"), None)
        if music:
            for i, sid in enumerate(music.get("sources") or []):
                if sid in scores:
                    scores[sid] = max(scores[sid], 52.0 - i * 2.0)

    for i, sid in enumerate(ai_priority or []):
        if sid not in scores:
            continue
        # 仅对已有规则相关度的信源叠加 AI/推荐优先级，避免无差别抬高用户勾选池。
        if scores[sid] < 12.0:
            continue
        scores[sid] += max(8.0, 22.0 - i * 2.0)

    scores["web"] = max(scores["web"], 22.0)
    if any("\u4e00" <= c <= "\u9fff" for c in query):
        scores["zhihu"] = max(scores["zhihu"], 18.0)

    return scores


def match_domain_route(query: str) -> dict[str, Any] | None:
    q = (query or "").strip().lower()
    if len(q) < 2:
        return None
    best: dict[str, Any] | None = None
    best_score = 0
    for route in _DOMAIN_ROUTES:
        score = sum(1 for kw in route["keywords"] if kw.lower() in q)
        if score > best_score:
            best_score = score
            best = route
    if best_score > 0:
        return best
    return None


def apply_source_routing(
    query: str,
    available: list[str],
    ai_recommended: list[str] | None = None,
    *,
    profile: str = "default",
    scores: dict[str, float] | None = None,
    score_breakdown: dict[str, dict[str, Any]] | None = None,
    ai_plan: dict[str, Any] | None = None,
    source_overrides: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """按话题解析本次采集信源（温和模式 + 可选 AI 融合分）。"""
    from osint_toolkit.collectors.source_resolve import resolve_search_sources

    resolved = resolve_search_sources(
        query,
        available,
        ai_recommended=ai_recommended,
        profile=profile,
        scores=scores,
        score_breakdown=score_breakdown,
        ai_plan=ai_plan,
        source_overrides=source_overrides,
    )
    route = match_domain_route(query)
    hint = resolved.get("hint") or ""
    if route and route.get("id") == "music" and resolved.get("mode") != "off":
        user_music = [s for s in (resolved.get("user_sources") or []) if s in _music_source_ids()]
        if _explicit_music_keywords(query) or user_music:
            hint = (hint + " B站可挖热评；音乐站以 SERP 摘要为主。").strip()

    return {
        "domain": resolved.get("domain") or "",
        "label": resolved.get("label") or "",
        "mode": resolved.get("mode") or "gentle",
        "recommended_sources": resolved.get("active_sources") or [],
        "active_sources": resolved.get("active_sources") or [],
        "user_sources": resolved.get("user_sources") or [],
        "auto_enabled": resolved.get("auto_enabled") or [],
        "skipped": resolved.get("skipped") or [],
        "scores": resolved.get("scores") or {},
        "score_breakdown": resolved.get("score_breakdown") or {},
        "rule_scores": resolved.get("rule_scores") or {},
        "source_plan": resolved.get("source_plan") or {},
        "is_cryptic": bool(resolved.get("is_cryptic")),
        "suggested_sources": resolved.get("auto_enabled") or [],
        "boost_site_domains": resolved.get("boost_site_domains") or [],
        "hint": hint,
    }
