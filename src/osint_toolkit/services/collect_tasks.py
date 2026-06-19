"""采集任务公平调度 / Fair collect task scheduling."""

from __future__ import annotations


def build_fair_collect_tasks(
    queries: list[str],
    sources: list[str],
    *,
    max_tasks: int,
) -> list[tuple[str, str]]:
    """按查询轮询分配 (source, query)，避免仅前几个扩展词占满配额。"""
    if max_tasks <= 0 or not queries or not sources:
        return []
    per_query = [[(source, q) for source in sources] for q in queries]
    tasks: list[tuple[str, str]] = []
    depth = 0
    while len(tasks) < max_tasks:
        progressed = False
        for queue in per_query:
            if depth < len(queue):
                tasks.append(queue[depth])
                progressed = True
                if len(tasks) >= max_tasks:
                    break
        if not progressed:
            break
        depth += 1
    return tasks
