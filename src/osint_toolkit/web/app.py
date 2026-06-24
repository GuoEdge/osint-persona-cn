"""FastAPI 应用 / FastAPI application."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from osint_toolkit.services.events import prune_old_events
from osint_toolkit.services.run_session import mark_stale_running_as_interrupted
from osint_toolkit.services.runs import cleanup_runs
from osint_toolkit.services.watch_scheduler import watch_scheduler_loop
from osint_toolkit.web.middleware import WebTokenMiddleware
from osint_toolkit.web.routes import api, pages

_STATIC = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    mark_stale_running_as_interrupted()
    try:
        cleanup_runs(older_than_days=30, keep_latest=20, dry_run=False)
    except Exception:  # noqa: BLE001
        pass
    try:
        prune_old_events(older_than_days=90)
    except Exception:  # noqa: BLE001
        pass
    scheduler_task = asyncio.create_task(watch_scheduler_loop())
    yield
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass
    from osint_toolkit.web.tasks import _async_tasks, shutdown_all_jobs

    shutdown_all_jobs()
    await asyncio.gather(*list(_async_tasks.values()), return_exceptions=True)


def create_app() -> FastAPI:
    app = FastAPI(title="OSINT Toolkit Web", version="0.1.0", lifespan=lifespan)
    app.add_middleware(WebTokenMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Osint-Token"],
    )
    app.include_router(pages.router)
    app.include_router(api.router)
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")
    return app
