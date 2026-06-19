"""Tests for search task queue and /api/search/tasks."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from osint_toolkit.web import tasks
from osint_toolkit.web.app import create_app


@pytest.fixture
def reset_tasks():
    tasks._jobs.clear()
    tasks._async_tasks.clear()
    tasks._search_queue.clear()
    yield
    for task in list(tasks._async_tasks.values()):
        if not task.done():
            task.cancel()
    tasks._jobs.clear()
    tasks._async_tasks.clear()
    tasks._search_queue.clear()


@pytest.fixture
def client():
    return TestClient(create_app())


@pytest.fixture
def one_concurrent_search(monkeypatch):
    monkeypatch.setattr("osint_toolkit.web.tasks._max_concurrent_searches", lambda: 1)


@pytest.fixture
def stub_async_tasks(monkeypatch):
    """Avoid needing a running event loop when unit-testing start_search_job."""

    def _capture(coro):
        coro.close()
        mock = MagicMock()
        mock.done.return_value = False
        return mock

    monkeypatch.setattr("osint_toolkit.web.tasks.asyncio.create_task", _capture)


def _empty_search_result(**kwargs):
    return {
        "run_id": kwargs.get("run_id") or "test-run",
        "items": [],
        "report": "",
        "report_path": None,
        "simulations": [],
    }


def test_search_tasks_endpoint_empty(client, reset_tasks):
    r = client.get("/api/search/tasks")
    assert r.status_code == 200
    assert r.json()["tasks"] == []


def test_start_search_job_queues_when_at_capacity(reset_tasks, one_concurrent_search, stub_async_tasks):
    first = tasks.start_search_job(query="topic-a", sources=["web"], no_ai=True)
    second = tasks.start_search_job(query="topic-b", sources=["web"], no_ai=True)

    assert first["status"] == "running"
    assert second["status"] == "queued"
    assert second["queue_position"] == 1
    assert tasks._count_running_searches() == 1

    listed = tasks.list_search_tasks()
    by_query = {t["query"]: t for t in listed}
    assert by_query["topic-a"]["status"] == "running"
    assert by_query["topic-b"]["status"] == "queued"


@pytest.mark.asyncio
async def test_drain_queue_after_first_completes(reset_tasks, one_concurrent_search):
    blockers: dict[str, asyncio.Event] = {}

    async def slow_search(**kwargs):
        run_id = kwargs["run_id"]
        blockers[run_id] = asyncio.Event()
        await blockers[run_id].wait()
        return _empty_search_result(run_id=run_id)

    with patch("osint_toolkit.services.search.run_search", new=AsyncMock(side_effect=slow_search)):
        first = tasks.start_search_job(query="first", sources=["web"], no_ai=True)
        second = tasks.start_search_job(query="second", sources=["web"], no_ai=True)
        run_first = first["run_id"]
        run_second = second["run_id"]

        for _ in range(50):
            await asyncio.sleep(0.05)
            if run_first in blockers:
                break
        blockers[run_first].set()
        for _ in range(50):
            await asyncio.sleep(0.05)
            job = tasks.get_job(run_second)
            if job and job.get("status") == "running":
                break
        job_second = tasks.get_job(run_second)
        assert job_second is not None
        assert job_second.get("status") == "running"

        for _ in range(50):
            await asyncio.sleep(0.05)
            if run_second in blockers:
                break
        blockers[run_second].set()
        for _ in range(50):
            await asyncio.sleep(0.05)
            job_done = tasks.get_job(run_first)
            if job_done and job_done.get("status") == "done":
                break
        assert tasks.get_job(run_first)["status"] == "done"


def test_cancel_queued_search(reset_tasks, one_concurrent_search, stub_async_tasks):
    first = tasks.start_search_job(query="hold", sources=["web"], no_ai=True)
    second = tasks.start_search_job(query="queued-one", sources=["web"], no_ai=True)
    queued_id = second["run_id"]

    assert tasks.cancel_job(queued_id) is True
    job = tasks.get_job(queued_id)
    assert job is not None
    assert job["status"] == "cancelled"
    assert tasks._queue_position(queued_id) is None
    assert first["run_id"] in tasks._jobs


def test_search_tasks_api_lists_jobs(client, reset_tasks, one_concurrent_search, stub_async_tasks):
    tasks.start_search_job(query="running", sources=["web"], no_ai=True)
    tasks.start_search_job(query="waiting", sources=["web"], no_ai=True)

    r = client.get("/api/search/tasks")
    assert r.status_code == 200
    by_query = {t["query"]: t for t in r.json()["tasks"]}
    assert by_query["running"]["status"] == "running"
    assert by_query["waiting"]["status"] == "queued"

    active = client.get("/api/search/active").json()["searches"]
    statuses = {s["query"]: s["status"] for s in active}
    assert statuses["running"] == "running"
    assert statuses["waiting"] == "queued"


def test_api_search_returns_queued_status(client, reset_tasks, one_concurrent_search, stub_async_tasks):
    tasks.start_search_job(query="topic-a", sources=["web"], no_ai=True)
    r2 = client.post("/api/search", json={"query": "topic-b", "sources": ["web"], "no_ai": True})

    assert r2.status_code == 200
    assert r2.json()["status"] == "queued"
    assert r2.json()["queue_position"] == 1


def test_trim_jobs_preserves_active_queued(reset_tasks, monkeypatch, one_concurrent_search, stub_async_tasks):
    monkeypatch.setattr(tasks, "_MAX_JOBS", 3)
    tasks.start_search_job(query="running", sources=["web"], no_ai=True)
    queued = tasks.start_search_job(query="waiting", sources=["web"], no_ai=True)
    queued_id = queued["run_id"]
    tasks._jobs["terminal-a"] = {"status": "done", "kind": "search", "query": "old-a"}
    tasks._jobs["terminal-b"] = {"status": "error", "kind": "search", "query": "old-b"}
    tasks._trim_jobs()
    assert tasks.get_job(queued_id) is not None
    assert tasks.get_job(queued_id)["status"] == "queued"
    assert tasks._queue_position(queued_id) == 1


def test_queue_full_raises(reset_tasks, monkeypatch, one_concurrent_search, stub_async_tasks):
    monkeypatch.setattr(tasks, "_max_queued_searches", lambda: 1)
    tasks.start_search_job(query="running", sources=["web"], no_ai=True)
    tasks.start_search_job(query="queued-one", sources=["web"], no_ai=True)
    with pytest.raises(tasks.SearchQueueFullError):
        tasks.start_search_job(query="queued-two", sources=["web"], no_ai=True)


def test_api_search_queue_full_429(client, reset_tasks, monkeypatch, one_concurrent_search, stub_async_tasks):
    monkeypatch.setattr(tasks, "_max_queued_searches", lambda: 1)
    tasks.start_search_job(query="running", sources=["web"], no_ai=True)
    tasks.start_search_job(query="queued-one", sources=["web"], no_ai=True)
    r = client.post("/api/search", json={"query": "queued-two", "sources": ["web"], "no_ai": True})
    assert r.status_code == 429


def test_cancel_orphan_queued_in_queue_only(reset_tasks, monkeypatch):
    monkeypatch.setattr(tasks, "_max_concurrent_searches", lambda: 1)
    run_id = tasks.new_run_id()
    tasks._search_queue.append((run_id, {"query": "orphan", "sources": ["web"], "no_ai": True}))
    assert tasks.cancel_job(run_id) is True
    assert tasks._queue_position(run_id) is None
