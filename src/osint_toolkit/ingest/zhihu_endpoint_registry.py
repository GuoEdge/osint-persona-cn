"""知乎成员 API 端点注册表 / Zhihu member API endpoint registry.

仅 PUBLISH_ENDPOINTS 用于账号同步。VOTE/BROWSE/ACTIVITY 已废弃（见 docs/ZHIHU_PERSONA.md）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

from osint_toolkit.http.client import HttpClient
from osint_toolkit.ingest.zhihu_activities import iter_api_data_items

logger = logging.getLogger(__name__)

LayerStatus = Literal["ok", "empty", "fail", "skip"]

# 用户/维护者可见的能力说明（写入 ingest 结果）
ZHIHU_PERSONA_CAPABILITY_NOTE = (
    "知乎 Cookie 同步稳定支持：收藏、关注、我发布的回答/文章/想法、Edge 浏览历史。"
    "赞同与官方浏览/动态 API 已下线，同步不再重试；赞同与日常浏览请安装扩展被动采集。"
)


@dataclass(frozen=True)
class EndpointSpec:
    key: str
    path: str
    referer: str = "https://www.zhihu.com/"
    page_size: int = 20


# 保留定义供探测脚本与扩展解析参考，账号同步不再调用
DEPRECATED_VOTE_ENDPOINTS: tuple[EndpointSpec, ...] = (
    EndpointSpec("voteanswers", "/api/v4/members/{token}/voteanswers"),
    EndpointSpec("vote_answers", "/api/v4/members/{token}/vote_answers"),
    EndpointSpec("answers_voted", "/api/v4/members/{token}/answers/voted"),
)
DEPRECATED_BROWSE_ENDPOINTS: tuple[EndpointSpec, ...] = (
    EndpointSpec("browsing_histories", "/api/v4/members/{token}/browsing_histories"),
)
DEPRECATED_ACTIVITY_ENDPOINTS: tuple[EndpointSpec, ...] = (
    EndpointSpec("activities", "/api/v4/members/{token}/activities"),
)

# 向后兼容别名（测试/旧 import）
VOTE_ENDPOINTS = DEPRECATED_VOTE_ENDPOINTS
BROWSE_ENDPOINTS = DEPRECATED_BROWSE_ENDPOINTS
ACTIVITY_ENDPOINTS = DEPRECATED_ACTIVITY_ENDPOINTS
ACTIVITIES_INCLUDE = "data[*].target,actor"

PUBLISH_ENDPOINTS: tuple[EndpointSpec, ...] = (
    EndpointSpec(
        "answers",
        "/api/v4/members/{token}/answers",
        referer="https://www.zhihu.com/people/{token}/answers",
    ),
    EndpointSpec(
        "articles",
        "/api/v4/members/{token}/articles",
        referer="https://www.zhihu.com/people/{token}/posts",
    ),
    EndpointSpec(
        "pins",
        "/api/v4/members/{token}/pins",
        referer="https://www.zhihu.com/people/{token}/pins",
    ),
)

# 知乎 Playwright 自动补洞已停用（实测 Cookie 模式 0 捕获）
ZHihu_PROBE_PAGES: tuple[dict[str, str], ...] = ()


def layer_status_from_count(count: int, *, attempted: bool = True) -> LayerStatus:
    if not attempted:
        return "skip"
    if count > 0:
        return "ok"
    return "empty" if attempted else "fail"


def _format_path(spec: EndpointSpec, token: str, offset: int, *, extra_query: str = "") -> str:
    base = spec.path.format(token=token)
    q = f"offset={offset}&limit={spec.page_size}"
    if extra_query:
        q = f"{extra_query}&{q}"
    return f"https://www.zhihu.com{base}?{q}"


def _format_referer(spec: EndpointSpec, token: str) -> str:
    return spec.referer.format(token=token)


async def paginate_member_api(
    client: HttpClient,
    token: str,
    specs: tuple[EndpointSpec, ...],
    *,
    limit: int = 500,
    extra_query: str = "",
) -> tuple[list[dict[str, Any]], str | None]:
    """Try each endpoint spec; return raw API items from first working chain."""
    for spec in specs:
        offset = 0
        collected: list[dict[str, Any]] = []
        seen: set[str] = set()
        try:
            while len(collected) < limit:
                url = _format_path(spec, token, offset, extra_query=extra_query)
                referer = _format_referer(spec, token)
                resp = await client.get(url, headers={"Referer": referer})
                if resp.status_code != 200:
                    break
                payload = resp.json()
                batch = iter_api_data_items(payload.get("data"))
                if not batch:
                    break
                for item in batch:
                    key = str(item.get("id") or item.get("url") or id(item))
                    if key in seen:
                        continue
                    seen.add(key)
                    collected.append(item)
                    if len(collected) >= limit:
                        break
                paging = payload.get("paging") or {}
                if paging.get("is_end") or len(batch) < spec.page_size:
                    break
                offset += spec.page_size
            if collected:
                return collected, spec.key
        except Exception as exc:  # noqa: BLE001
            logger.debug("zhihu endpoint %s failed: %s", spec.key, exc)
            continue
    return [], None
