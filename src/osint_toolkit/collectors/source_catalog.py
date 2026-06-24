"""搜罗信源目录 / Search source catalog (labels, categories, defaults)."""

from __future__ import annotations

import functools
from typing import Any

from osint_toolkit.collectors.source_auth import auth_fields_for_catalog

# kind: native = 独立采集器；site = site:domain SERP
# depth: native | serp | hybrid — 采集深度诚实标注
_HYBRID_SOURCES = frozenset({"zhihu", "bilibili"})
_COMMENT_MINE_SOURCES = frozenset({"zhihu", "bilibili", "v2ex"})
_EXPAND_SOURCES = frozenset({"zhihu"})
# content_locale: zh | intl | mixed — 主内容语言倾向
# accept_foreign_queries: 采集时是否合并外文拓展词
_SOURCE_LOCALE: dict[str, tuple[str, bool]] = {
    "zhihu": ("zh", False),
    "bilibili": ("zh", False),
    "weixin": ("zh", False),
    "v2ex": ("zh", False),
    "tieba": ("zh", False),
    "xiaohongshu": ("zh", False),
    "jike": ("zh", False),
    "jianshu": ("zh", False),
    "weibo": ("zh", False),
    "nga": ("zh", False),
    "maimai": ("zh", False),
    "ithome": ("zh", False),
    "sspai": ("zh", False),
    "juejin": ("zh", False),
    "chiphell": ("zh", False),
    "smzdm": ("zh", False),
    "gcores": ("zh", False),
    "kr36": ("zh", False),
    "huxiu": ("zh", False),
    "caixin": ("zh", False),
    "thepaper": ("zh", False),
    "ifeng": ("zh", False),
    "douban": ("zh", False),
    "xiaoyuzhou": ("zh", False),
    "ximalaya": ("zh", False),
    "netease_music": ("zh", False),
    "qq_music": ("zh", False),
    "kugou": ("zh", False),
    "migu": ("zh", False),
    "web": ("mixed", True),
    "github": ("intl", True),
    "reddit": ("intl", True),
    "hackernews": ("intl", True),
    "solidot": ("mixed", True),
    "rss": ("mixed", True),
}
# 综合性原生信源：用户勾选后不因领域包弱分被跳过（音乐站除外）
_COMPREHENSIVE_NATIVE_CATEGORIES = frozenset({"core", "community"})


def _entry_capabilities(entry: dict[str, Any]) -> dict[str, Any]:
    sid = str(entry.get("id") or "")
    kind = str(entry.get("kind") or "site")
    if entry.get("depth"):
        depth = str(entry["depth"])
    elif sid in _HYBRID_SOURCES:
        depth = "hybrid"
    elif kind == "native":
        depth = "native"
    else:
        depth = "serp"
    caps = {
        "kind": kind,
        "depth": depth,
        "comment_mine": bool(entry.get("comment_mine", sid in _COMMENT_MINE_SOURCES)),
        "expand": bool(entry.get("expand", sid in _EXPAND_SOURCES)),
        "fetch_content": bool(entry.get("fetch_content", str(entry.get("category") or "") != "music")),
    }
    caps.update(auth_fields_for_catalog(sid))
    locale, accept_foreign = _SOURCE_LOCALE.get(sid, ("zh", False))
    caps["content_locale"] = str(entry.get("content_locale") or locale)
    caps["accept_foreign_queries"] = bool(entry.get("accept_foreign_queries", accept_foreign))
    return caps


SOURCE_ENTRIES: list[dict[str, Any]] = [
    # —— 核心（默认勾选）——
    {
        "id": "zhihu",
        "label": "知乎",
        "category": "core",
        "kind": "native",
        "default": True,
        "description": "问答、专栏、观点；需 Cookie 或开放平台 Key",
    },
    {
        "id": "bilibili",
        "label": "B站",
        "category": "core",
        "kind": "native",
        "default": True,
        "description": "视频、UP 主、弹幕文化；支持热评挖掘",
    },
    {
        "id": "web",
        "label": "网页",
        "category": "core",
        "kind": "native",
        "default": True,
        "description": "Bing/SERP 全网搜索，含配置中的垂直站点补搜",
    },
    {
        "id": "weixin",
        "label": "搜狗微信公众平台",
        "category": "core",
        "kind": "native",
        "default": True,
        "description": "搜狗微信公众平台的公众号文章检索（非微信客户端），含阅读量过滤",
    },
    # —— 社区 ——
    {
        "id": "v2ex",
        "label": "V2EX",
        "category": "community",
        "kind": "native",
        "default": False,
        "description": "技术社区帖子与讨论",
    },
    {
        "id": "weibo",
        "label": "微博",
        "category": "social",
        "kind": "site",
        "domain": "weibo.com",
        "default": False,
        "description": "热搜话题、大 V 观点、实时舆情",
    },
    {
        "id": "nga",
        "label": "NGA",
        "category": "gaming",
        "kind": "site",
        "domain": "ngabbs.com",
        "default": False,
        "description": "游戏、数码、二次元深度讨论串",
    },
    {
        "id": "rss",
        "label": "RSS",
        "category": "community",
        "kind": "native",
        "default": False,
        "description": "config 中 rss_feeds 订阅源",
    },
    {
        "id": "jike",
        "label": "即刻",
        "category": "social",
        "kind": "site",
        "domain": "okjike.com",
        "default": False,
        "description": "兴趣圈子动态、短观点与话题讨论",
    },
    {
        "id": "tieba",
        "label": "百度贴吧",
        "category": "community",
        "kind": "site",
        "domain": "tieba.baidu.com",
        "default": False,
        "description": "垂直社区帖子、吃瓜与长尾讨论",
    },
    {
        "id": "jianshu",
        "label": "简书",
        "category": "community",
        "kind": "site",
        "domain": "jianshu.com",
        "default": False,
        "description": "个人专栏、随笔与深度长文",
    },
    {
        "id": "reddit",
        "label": "Reddit",
        "category": "community",
        "kind": "site",
        "domain": "reddit.com",
        "default": False,
        "description": "英文社区帖子与讨论串",
    },
    {
        "id": "xiaohongshu",
        "label": "小红书",
        "category": "social",
        "kind": "site",
        "domain": "xiaohongshu.com",
        "default": False,
        "description": "生活方式笔记、测评与种草内容",
    },
    {
        "id": "maimai",
        "label": "脉脉",
        "category": "social",
        "kind": "site",
        "domain": "maimai.cn",
        "default": False,
        "description": "职场动态、行业八卦与公司舆情",
    },
    # —— 科技数码 ——
    {
        "id": "ithome",
        "label": "IT之家",
        "category": "tech",
        "kind": "site",
        "domain": "ithome.com",
        "default": False,
        "description": "消费电子、系统更新、发布会快讯",
    },
    {
        "id": "sspai",
        "label": "少数派",
        "category": "tech",
        "kind": "site",
        "domain": "sspai.com",
        "default": False,
        "description": "效率工具、数字生活方式深度文",
    },
    {
        "id": "juejin",
        "label": "掘金",
        "category": "tech",
        "kind": "site",
        "domain": "juejin.cn",
        "default": False,
        "description": "前端/后端技术文章与教程",
    },
    {
        "id": "solidot",
        "label": "Solidot",
        "category": "tech",
        "kind": "site",
        "domain": "solidot.org",
        "default": False,
        "description": "开源与技术新闻聚合",
    },
    {
        "id": "github",
        "label": "GitHub",
        "category": "tech",
        "kind": "native",
        "default": False,
        "description": "GitHub Search API 仓库检索，不足时回退 site:github.com",
        "depth": "native",
        "comment_mine": False,
        "expand": False,
    },
    {
        "id": "hackernews",
        "label": "Hacker News",
        "category": "tech",
        "kind": "site",
        "domain": "news.ycombinator.com",
        "default": False,
        "description": "英文技术社区热点与评论",
    },
    {
        "id": "chiphell",
        "label": "Chiphell",
        "category": "tech",
        "kind": "site",
        "domain": "chiphell.com",
        "default": False,
        "description": "硬件发烧友、装机与数码深度讨论",
    },
    {
        "id": "smzdm",
        "label": "什么值得买",
        "category": "tech",
        "kind": "site",
        "domain": "smzdm.com",
        "default": False,
        "description": "消费数码测评、好价与选购经验",
    },
    {
        "id": "gcores",
        "label": "机核",
        "category": "gaming",
        "kind": "site",
        "domain": "gcores.com",
        "default": False,
        "description": "游戏文化、评测与播客式长文",
    },
    # —— 商业观察 ——
    {
        "id": "kr36",
        "label": "36氪",
        "category": "business",
        "kind": "site",
        "domain": "36kr.com",
        "default": False,
        "description": "创投、商业、产业动态",
    },
    {
        "id": "huxiu",
        "label": "虎嗅",
        "category": "business",
        "kind": "site",
        "domain": "huxiu.com",
        "default": False,
        "description": "商业分析与行业评论",
    },
    {
        "id": "caixin",
        "label": "财新",
        "category": "business",
        "kind": "site",
        "domain": "caixin.com",
        "default": False,
        "description": "财经新闻、政策解读与深度报道",
    },
    {
        "id": "thepaper",
        "label": "澎湃新闻",
        "category": "business",
        "kind": "site",
        "domain": "thepaper.cn",
        "default": False,
        "description": "时政、社会与财经热点追踪",
    },
    {
        "id": "ifeng",
        "label": "凤凰网",
        "category": "business",
        "kind": "site",
        "domain": "ifeng.com",
        "default": False,
        "description": "综合新闻与评论",
    },
    # —— 音乐 ——
    {
        "id": "netease_music",
        "label": "网易云音乐",
        "category": "music",
        "kind": "site",
        "domain": "music.163.com",
        "default": False,
        "depth": "serp",
        "fetch_content": False,
        "description": "仅搜索引擎 site: 摘要（不登录官网；不抓取需登录的曲目页）",
    },
    {
        "id": "qq_music",
        "label": "QQ音乐",
        "category": "music",
        "kind": "site",
        "domain": "y.qq.com",
        "default": False,
        "depth": "serp",
        "fetch_content": False,
        "description": "仅搜索引擎 site: 摘要（不登录官网；不抓取需登录的曲目页）",
    },
    {
        "id": "kugou",
        "label": "酷狗音乐",
        "category": "music",
        "kind": "site",
        "domain": "kugou.com",
        "default": False,
        "depth": "serp",
        "fetch_content": False,
        "description": "仅搜索引擎 site: 摘要（不登录官网）",
    },
    {
        "id": "migu",
        "label": "咪咕音乐",
        "category": "music",
        "kind": "site",
        "domain": "music.migu.cn",
        "default": False,
        "depth": "serp",
        "fetch_content": False,
        "description": "仅搜索引擎 site: 摘要（不登录官网）",
    },
    # —— 文化文娱 ——
    {
        "id": "douban",
        "label": "豆瓣",
        "category": "culture",
        "kind": "site",
        "domain": "douban.com",
        "default": False,
        "description": "书影音评分与长评",
    },
    {
        "id": "xiaoyuzhou",
        "label": "小宇宙",
        "category": "culture",
        "kind": "site",
        "domain": "xiaoyuzhoufm.com",
        "default": False,
        "description": "播客节目与单集（观点类长内容）",
    },
    {
        "id": "ximalaya",
        "label": "喜马拉雅",
        "category": "culture",
        "kind": "site",
        "domain": "ximalaya.com",
        "default": False,
        "description": "有声书、播客与音频节目",
    },
]

_CATALOG_DISPLAY: list[dict[str, Any]] = [
    {"id": "core", "label": "常用", "categories": ["core"], "tier": "primary"},
    {
        "id": "community_hub",
        "label": "社区与舆情",
        "categories": ["community", "social", "gaming"],
        "tier": "extended",
    },
    {"id": "tech", "label": "科技数码", "categories": ["tech"], "tier": "extended"},
    {"id": "business", "label": "商业财经", "categories": ["business"], "tier": "extended"},
    {"id": "music", "label": "音乐", "categories": ["music"], "tier": "extended"},
    {"id": "culture", "label": "文化文娱", "categories": ["culture"], "tier": "extended"},
]

# legacy category on each entry — used by routing/planner, not necessarily UI grouping
_CATEGORY_LABELS: dict[str, str] = {
    "core": "核心来源",
    "community": "社区",
    "social": "社交舆情",
    "gaming": "游戏",
    "tech": "科技数码",
    "business": "商业观察",
    "music": "音乐",
    "culture": "文化文娱",
}


def get_source_entries() -> list[dict[str, Any]]:
    return [dict(e) for e in SOURCE_ENTRIES]


def get_source_labels() -> dict[str, str]:
    return {str(e["id"]): str(e["label"]) for e in SOURCE_ENTRIES}


def get_default_source_ids() -> list[str]:
    return [str(e["id"]) for e in SOURCE_ENTRIES if e.get("default")]


def get_all_source_ids() -> list[str]:
    return [str(e["id"]) for e in SOURCE_ENTRIES]


def get_source_locale_meta(source_id: str) -> dict[str, Any]:
    """Return content_locale and accept_foreign_queries for a catalog source."""
    entry = next((e for e in SOURCE_ENTRIES if str(e.get("id")) == source_id), None)
    if entry:
        caps = _entry_capabilities(entry)
        return {
            "content_locale": caps.get("content_locale", "zh"),
            "accept_foreign_queries": bool(caps.get("accept_foreign_queries")),
        }
    locale, accept_foreign = _SOURCE_LOCALE.get(source_id, ("zh", False))
    return {"content_locale": locale, "accept_foreign_queries": accept_foreign}


def any_source_accepts_foreign(sources: list[str]) -> bool:
    return any(get_source_locale_meta(s).get("accept_foreign_queries") for s in sources)


def comprehensive_native_source_ids() -> frozenset[str]:
    """知乎/B站/V2EX 等综合性原生采集器：领域包只用于加分与垂直站自动启用，不用于跳过用户勾选。"""
    return frozenset(
        str(e["id"])
        for e in SOURCE_ENTRIES
        if e.get("kind") == "native"
        and str(e.get("category") or "") in _COMPREHENSIVE_NATIVE_CATEGORIES
    )


def get_site_search_entries() -> list[dict[str, Any]]:
    return [e for e in SOURCE_ENTRIES if e.get("kind") == "site" and e.get("domain")]


@functools.lru_cache(maxsize=1)
def get_catalog_grouped() -> list[dict[str, Any]]:
    by_cat: dict[str, list[dict[str, Any]]] = {}
    for entry in SOURCE_ENTRIES:
        cat = str(entry.get("category") or "other")
        caps = _entry_capabilities(entry)
        by_cat.setdefault(cat, []).append(
            {
                "id": entry["id"],
                "label": entry["label"],
                "description": entry.get("description") or "",
                "default": bool(entry.get("default")),
                "category": cat,
                **caps,
            }
        )

    def _sort_sources(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        def rank(item: dict[str, Any]) -> tuple[int, str]:
            depth = str(item.get("depth") or "")
            kind_rank = 0 if depth in ("native", "hybrid") else 1
            return (kind_rank, str(item.get("label") or ""))

        return sorted(items, key=rank)

    out: list[dict[str, Any]] = []
    for spec in _CATALOG_DISPLAY:
        items: list[dict[str, Any]] = []
        for cat in spec["categories"]:
            items.extend(by_cat.pop(cat, []))
        if not items:
            continue
        out.append(
            {
                "id": spec["id"],
                "label": spec["label"],
                "tier": spec["tier"],
                "sources": _sort_sources(items),
            }
        )
    for cat, items in by_cat.items():
        if not items:
            continue
        out.append(
            {
                "id": cat,
                "label": _CATEGORY_LABELS.get(cat, cat),
                "tier": "extended",
                "sources": _sort_sources(items),
            }
        )
    return out


def merge_source_priority(user_sources: list[str], priority: list[str] | None) -> list[str]:
    """用户勾选为准，priority 仅决定采集顺序，不裁掉任何已选信源。"""
    from osint_toolkit.collectors.registry import COLLECTORS

    user = [s for s in user_sources if s in COLLECTORS]
    if not user:
        user = list(COLLECTORS.keys())[:4]
    if not priority:
        return user
    ordered = [s for s in priority if s in user]
    tail = [s for s in user if s not in ordered]
    return ordered + tail
