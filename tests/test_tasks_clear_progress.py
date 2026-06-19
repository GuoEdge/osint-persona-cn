"""full_sync / playwright 任务进度清理测试."""

from __future__ import annotations

import asyncio

import pytest

from osint_toolkit.pipeline.progress import get_progress, init_progress
from osint_toolkit.web import tasks


@pytest.mark.asyncio
async def test_full_sync_finally_clears_progress(monkeypatch):
    job_id = "20260101-120000-ff000001"

    async def fake_sync(**_kwargs):
        return {"steps": []}

    monkeypatch.setattr("osint_toolkit.services.unified_sync.run_full_sync", fake_sync)
    init_progress(job_id)
    tasks._jobs[job_id] = {"status": "running", "kind": "full_sync", "steps": []}
    await tasks._execute_full_sync(job_id)
    assert get_progress(job_id) is None
