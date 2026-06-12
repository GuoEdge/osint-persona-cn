"""字幕处理 / Subtitle processing."""

from __future__ import annotations


def parse_subtitle_json(body: str) -> str:
    """解析 B 站字幕 JSON 为纯文本。"""
    import json

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return body
    lines: list[str] = []
    for item in data.get("body", []):
        content = item.get("content", "")
        if content:
            lines.append(content)
    return "\n".join(lines)
