"""评论挖掘信源注册表 / Comment mining source registry."""

from __future__ import annotations

COMMENT_MINE_SOURCES: set[str] = {"bilibili", "zhihu", "v2ex"}


def supports_comment_mine(source: str) -> bool:
    return source in COMMENT_MINE_SOURCES


def register_comment_mine(source: str) -> None:
    COMMENT_MINE_SOURCES.add(source)
