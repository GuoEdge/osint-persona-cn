"""话题聚类 / Topic clustering."""

from __future__ import annotations

from collections import defaultdict

from osint_toolkit.models.intel_item import IntelItem


def cluster_items(items: list[IntelItem]) -> list[dict]:
    buckets: dict[str, list[IntelItem]] = defaultdict(list)
    for item in items:
        key = item.source
        buckets[key].append(item)
    clusters = []
    for source, group in buckets.items():
        clusters.append({"name": source, "items": group, "count": len(group)})
    return clusters
