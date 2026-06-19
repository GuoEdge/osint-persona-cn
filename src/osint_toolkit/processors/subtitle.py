"""字幕处理 / Subtitle processing."""

from __future__ import annotations


def pick_subtitle_track(subtitles: list[dict], *, prefer: str = "ai_first") -> dict | None:
    """优选字幕轨。

    prefer:
      - ai_first（默认）：AI/自动生成中文轨优先
      - cc_first：人工/CC 中文轨优先，其次 AI
    """
    if not subtitles:
        return None

    def score(track: dict) -> int:
        lan_doc = str(track.get("lan_doc") or "")
        lan = str(track.get("lan") or "").lower()
        is_ai = any(k in lan_doc for k in ("自动", "AI", "ai", "机翻", "智能")) or track.get("ai_type") in (
            1,
            "1",
        ) or track.get("ai_status") in (1, "1")
        is_cc = str(track.get("type") or "") in ("1", "cc") or (
            "中文" in lan_doc and "自动" not in lan_doc and "AI" not in lan_doc
        )
        points = 0
        if prefer == "cc_first":
            if is_cc:
                points += 300
            if is_ai:
                points += 120
        else:
            if is_ai:
                points += 200
            if is_cc:
                points += 160
        if "zh" in lan or "中文" in lan_doc or lan in {"zh-cn", "zh-hans"}:
            points += 80
        if str(track.get("type") or "") in ("1", "cc"):
            points += 40
        return points

    return max(subtitles, key=score)


def parse_subtitle_json(body: str) -> str:
    """解析 B 站字幕 JSON 为纯文本。"""
    import json

    text = (body or "").strip()
    if not text:
        return ""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return text if len(text) < 50000 else ""

    lines: list[str] = []

    def _append_from_items(items: list) -> None:
        for item in items:
            if isinstance(item, dict):
                content = str(item.get("content") or item.get("text") or "").strip()
                if content:
                    lines.append(content)
            elif isinstance(item, str) and item.strip():
                lines.append(item.strip())

    if isinstance(data, dict):
        body_items = data.get("body")
        if isinstance(body_items, list):
            _append_from_items(body_items)
        subs = data.get("subtitles")
        if isinstance(subs, list):
            _append_from_items(subs)
    elif isinstance(data, list):
        _append_from_items(data)

    return "\n".join(lines)
