"""观看诚意分析 / Engagement sincerity."""

from __future__ import annotations


def engagement_sincerity(
    *,
    duration_sec: int,
    progress: float,
    foreground_sec: int | None = None,
    entry: str = "unknown",
) -> dict:
    effective = duration_sec * progress
    if duration_sec < 60:
        sincerity = "casual" if effective < 10 else "uncertain"
        confidence = 0.4
    elif progress >= 0.7:
        sincerity = "serious"
        confidence = 0.75
    elif progress >= 0.35:
        sincerity = "uncertain"
        confidence = 0.55
    else:
        sincerity = "casual"
        confidence = 0.5
    if entry == "search":
        confidence = min(1.0, confidence + 0.1)
    if foreground_sec is not None and duration_sec > 0:
        ratio = foreground_sec / duration_sec
        if ratio < 0.3 and progress > 0.5:
            sincerity = "casual"
            confidence = 0.45
    return {"engagement_sincerity": sincerity, "confidence": round(confidence, 2)}
