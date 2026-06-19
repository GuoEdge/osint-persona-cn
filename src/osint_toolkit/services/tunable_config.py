"""Web 可调运行参数 / User-tunable config sections for settings UI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from osint_toolkit.utils.config import DEFAULT_CONFIG, load_config
from osint_toolkit.utils.secrets import save_user_config_patch

FieldType = Literal["int", "float", "bool", "select"]


@dataclass(frozen=True)
class TunableFieldSpec:
    key: str
    path: tuple[str, ...]
    label: str
    field_type: FieldType
    description: str = ""
    min_value: float | None = None
    max_value: float | None = None
    step: float | None = None
    options: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class TunableGroupSpec:
    id: str
    title: str
    description: str
    fields: tuple[TunableFieldSpec, ...]


def _field(
    key: str,
    path: tuple[str, ...],
    label: str,
    field_type: FieldType,
    *,
    description: str = "",
    min_value: float | None = None,
    max_value: float | None = None,
    step: float | None = None,
    options: tuple[tuple[str, str], ...] = (),
) -> TunableFieldSpec:
    return TunableFieldSpec(
        key=key,
        path=path,
        label=label,
        field_type=field_type,
        description=description,
        min_value=min_value,
        max_value=max_value,
        step=step,
        options=options,
    )


TUNABLE_GROUPS: tuple[TunableGroupSpec, ...] = (
    TunableGroupSpec(
        id="search_concurrency",
        title="搜罗并发",
        description="控制同时运行的搜罗任务数量；超出上限的任务会进入队列。",
        fields=(
            _field(
                "search.max_concurrent_searches",
                ("search", "max_concurrent_searches"),
                "同时运行搜罗数",
                "int",
                description="建议 1～3，过高可能占用过多 CPU / 浏览器资源。进行中搜罗不受本次修改影响。",
                min_value=1,
                max_value=8,
            ),
            _field(
                "search.max_queued_searches",
                ("search", "max_queued_searches"),
                "排队任务上限",
                "int",
                description="超出并发上限后最多允许多少个任务排队。",
                min_value=1,
                max_value=100,
            ),
        ),
    ),
    TunableGroupSpec(
        id="search_fast",
        title="搜罗加速",
        description="关联词发现、知乎深度采集与 AI 摘要规模；调高可加速但可能漏信息或增加 API 消耗。",
        fields=(
            _field(
                "search.discover_aliases",
                ("search", "discover_aliases"),
                "联网发现关联词",
                "bool",
                description="关闭可跳过 alias_discover 阶段以加速。",
            ),
            _field(
                "search.zhihu_aggressive",
                ("search", "zhihu_aggressive"),
                "知乎深度采集",
                "bool",
                description="关闭可减少知乎请求量。",
            ),
            _field(
                "search.collect_early_stop_items",
                ("search", "collect_early_stop_items"),
                "采集提前结束阈值",
                "int",
                description="采够足够相关内容后提前结束；0 表示不提前结束。",
                min_value=0,
                max_value=200,
            ),
            _field(
                "search.ai_summarize_top",
                ("search", "ai_summarize_top"),
                "AI 摘要条数",
                "int",
                description="送入 AI 摘要的头部结果数量。",
                min_value=0,
                max_value=50,
            ),
            _field(
                "search.zhihu_global_collect_sem",
                ("search", "zhihu_global_collect_sem"),
                "全进程知乎采集并发",
                "int",
                description="多任务并行时共享的知乎采集上限。",
                min_value=1,
                max_value=8,
            ),
        ),
    ),
    TunableGroupSpec(
        id="search_collect",
        title="搜罗采集",
        description="关联词扩展与评论挖掘相关参数。",
        fields=(
            _field(
                "search.max_expanded_queries",
                ("search", "max_expanded_queries"),
                "扩展查询上限",
                "int",
                description="单次搜罗最多并行使用的扩展关键词数量。",
                min_value=1,
                max_value=20,
            ),
            _field(
                "search.comment_mine_top",
                ("search", "comment_mine_top"),
                "评论挖掘条数",
                "int",
                description="对排名前 N 的结果拉取热评/弹幕等。",
                min_value=0,
                max_value=30,
            ),
            _field(
                "search.include_slurs",
                ("search", "include_slurs"),
                "扩展贬义/黑称关联词",
                "bool",
                description="开启后关联词发现可能包含敏感别名。",
            ),
        ),
    ),
    TunableGroupSpec(
        id="zhihu_openapi",
        title="知乎开放平台",
        description="官方 API 搜索与限流；需先在上方配置 Access Secret。",
        fields=(
            _field(
                "zhihu.openapi.enabled",
                ("zhihu", "openapi", "enabled"),
                "启用 OpenAPI",
                "bool",
            ),
            _field(
                "zhihu.openapi.prefer_search",
                ("zhihu", "openapi", "prefer_search"),
                "优先 OpenAPI 搜索",
                "bool",
                description="失败时自动回退 Cookie / Playwright / SERP。",
            ),
            _field(
                "zhihu.openapi.merge_search_v3",
                ("zhihu", "openapi", "merge_search_v3"),
                "结果不足时合并 search_v3",
                "bool",
            ),
            _field(
                "zhihu.openapi.min_request_interval_sec",
                ("zhihu", "openapi", "min_request_interval_sec"),
                "请求最小间隔（秒）",
                "float",
                description="避免 Code=30001 second limit exceeded；多任务时全局限流。",
                min_value=0,
                max_value=10,
                step=0.1,
            ),
            _field(
                "zhihu.openapi.rate_limit_retry_max",
                ("zhihu", "openapi", "rate_limit_retry_max"),
                "限流重试次数",
                "int",
                min_value=0,
                max_value=10,
            ),
            _field(
                "zhihu.openapi.rate_limit_retry_base_sec",
                ("zhihu", "openapi", "rate_limit_retry_base_sec"),
                "限流重试基础等待（秒）",
                "float",
                min_value=0.1,
                max_value=30,
                step=0.1,
            ),
            _field(
                "zhihu.openapi.features.global_search",
                ("zhihu", "openapi", "features", "global_search"),
                "启用全网搜索",
                "bool",
                description="OpenAPI global_search（含站外链接）。",
            ),
        ),
    ),
    TunableGroupSpec(
        id="ai_behavior",
        title="AI 行为",
        description="画像注入、自动重建与扩展停留收录策略。",
        fields=(
            _field(
                "ai.persona_inject",
                ("ai", "persona_inject"),
                "注入用户画像",
                "bool",
            ),
            _field(
                "ai.dwell_save_no_ai",
                ("ai", "dwell_save_no_ai"),
                "高停留收录跳过 AI",
                "bool",
                description="节省 API 调用。",
            ),
            _field(
                "ai.auto_persona_rebuild",
                ("ai", "auto_persona_rebuild"),
                "画像自动重建",
                "select",
                options=(("off", "关闭"), ("prompt", "达阈值后提醒"), ("auto", "达阈值后自动重建")),
            ),
            _field(
                "ai.auto_persona_rebuild_threshold",
                ("ai", "auto_persona_rebuild_threshold"),
                "画像重建阈值（条）",
                "int",
                min_value=10,
                max_value=500,
            ),
        ),
    ),
)

_FIELD_BY_KEY: dict[str, TunableFieldSpec] = {
    field.key: field for group in TUNABLE_GROUPS for field in group.fields
}


def _nested_get(data: dict[str, Any], path: tuple[str, ...]) -> Any:
    cur: Any = data
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _default_for_path(path: tuple[str, ...]) -> Any:
    return _nested_get(DEFAULT_CONFIG, path)


def _coerce_value(spec: TunableFieldSpec, raw: Any) -> Any:
    if spec.field_type == "bool":
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            lowered = raw.strip().lower()
            if lowered in {"1", "true", "yes", "on"}:
                return True
            if lowered in {"0", "false", "no", "off"}:
                return False
        raise ValueError(f"{spec.label} 需要布尔值")
    if spec.field_type == "int":
        value = int(raw)
        if spec.min_value is not None and value < spec.min_value:
            raise ValueError(f"{spec.label} 不能小于 {int(spec.min_value)}")
        if spec.max_value is not None and value > spec.max_value:
            raise ValueError(f"{spec.label} 不能大于 {int(spec.max_value)}")
        return value
    if spec.field_type == "float":
        value = float(raw)
        if spec.min_value is not None and value < spec.min_value:
            raise ValueError(f"{spec.label} 不能小于 {spec.min_value}")
        if spec.max_value is not None and value > spec.max_value:
            raise ValueError(f"{spec.label} 不能大于 {spec.max_value}")
        return value
    if spec.field_type == "select":
        text = str(raw).strip()
        allowed = {opt[0] for opt in spec.options}
        if text not in allowed:
            raise ValueError(f"{spec.label} 无效选项")
        return text
    raise ValueError(f"未知字段类型: {spec.field_type}")


def _field_payload(spec: TunableFieldSpec, cfg: dict[str, Any]) -> dict[str, Any]:
    value = _nested_get(cfg, spec.path)
    if value is None:
        value = _default_for_path(spec.path)
    payload: dict[str, Any] = {
        "key": spec.key,
        "label": spec.label,
        "type": spec.field_type,
        "description": spec.description,
        "value": value,
    }
    if spec.min_value is not None:
        payload["min"] = spec.min_value
    if spec.max_value is not None:
        payload["max"] = spec.max_value
    if spec.step is not None:
        payload["step"] = spec.step
    if spec.options:
        payload["options"] = [{"value": v, "label": lbl} for v, lbl in spec.options]
    return payload


def _format_summary_value(spec: TunableFieldSpec, value: Any) -> str:
    if spec.field_type == "bool":
        return "开" if value else "关"
    if spec.field_type == "select" and spec.options:
        for opt_val, opt_label in spec.options:
            if opt_val == value:
                return opt_label
    return str(value)


def _group_summary(group: TunableGroupSpec, cfg: dict[str, Any]) -> str:
    parts: list[str] = []
    for field in group.fields:
        value = _nested_get(cfg, field.path)
        if value is None:
            value = _default_for_path(field.path)
        parts.append(f"{field.label} {_format_summary_value(field, value)}")
    return " · ".join(parts[:3]) + (" …" if len(parts) > 3 else "")


def list_tunable_groups() -> dict[str, Any]:
    cfg = load_config()
    groups = []
    for group in TUNABLE_GROUPS:
        groups.append(
            {
                "id": group.id,
                "title": group.title,
                "description": group.description,
                "summary": _group_summary(group, cfg),
                "fields": [_field_payload(field, cfg) for field in group.fields],
            }
        )
    return {"groups": groups}


def _nested_set(root: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    cur = root
    for key in path[:-1]:
        nxt = cur.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[key] = nxt
        cur = nxt
    cur[path[-1]] = value


def patch_tunable_values(values: dict[str, Any]) -> dict[str, Any]:
    if not values:
        raise ValueError("未提供任何参数")
    patch: dict[str, Any] = {}
    applied: dict[str, Any] = {}
    for key, raw in values.items():
        spec = _FIELD_BY_KEY.get(key)
        if not spec:
            raise ValueError(f"未知参数: {key}")
        coerced = _coerce_value(spec, raw)
        _nested_set(patch, spec.path, coerced)
        applied[key] = coerced
    config_path = save_user_config_patch(patch)
    return {"ok": True, "config_path": config_path, "applied": applied, "groups": list_tunable_groups()["groups"]}
