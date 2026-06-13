"""字幕处理 / Subtitle processing."""

from __future__ import annotations


def pick_subtitle_track(subtitles: list[dict]) -> dict | None:
    """优选字幕轨：AI/自动生成的中文轨优先，其次 CC/中文，最后第一条。"""
    if not subtitles:
        return None

    def score(track: dict) -> int:
        lan_doc = str(track.get("lan_doc") or "")
        lan = str(track.get("lan") or "").lower()
        points = 0
        if any(k in lan_doc for k in ("自动", "AI", "ai", "机翻", "智能")):
            points += 200
        if track.get("ai_type") in (1, "1") or track.get("ai_status") in (1, "1"):
            points += 200
        if "zh" in lan or "中文" in lan_doc or lan in {"zh-cn", "zh-hans"}:
            points += 80
        if str(track.get("type") or "") in ("1", "cc"):
            points += 40
        return points

    return max(subtitles, key=score)


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
