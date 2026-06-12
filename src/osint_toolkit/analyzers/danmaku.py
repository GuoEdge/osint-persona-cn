"""弹幕聚合 / Danmaku aggregation."""

from __future__ import annotations

from collections import Counter


def aggregate_danmaku(lines: list[str], top_n: int = 10) -> list[dict]:
    counter = Counter(line.strip() for line in lines if line.strip())
    return [{"text": text, "count": count} for text, count in counter.most_common(top_n)]
