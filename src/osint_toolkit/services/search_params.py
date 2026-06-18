"""搜罗 pipeline 与研究会话参数分界。"""

from __future__ import annotations

from typing import Any

# run_search() 接受的参数
SEARCH_PIPELINE_KEYS = frozenset({
    "query",
    "sources",
    "limit",
    "digest",
    "trace",
    "profile",
    "ai_instruct",
    "no_ai",
    "no_simulate",
    "disabled_ai_steps",
    "deep_top",
    "comment_mine_top",
    "include_slurs",
    "run_id",
})

# 仅落盘 / 研究树，不传入 pipeline
SEARCH_SESSION_KEYS = frozenset({
    "tree_id",
    "parent_node_id",
    "fork_from_run_id",
    "create_tree",
})


def pipeline_search_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in kwargs.items() if k in SEARCH_PIPELINE_KEYS and v is not None}


def strip_session_keys(kwargs: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in kwargs.items() if k not in SEARCH_SESSION_KEYS}
