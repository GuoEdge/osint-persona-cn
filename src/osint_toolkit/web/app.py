"""FastAPI 应用 / FastAPI application."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from osint_toolkit.services.run_session import mark_stale_running_as_interrupted
from osint_toolkit.web.routes import api, pages

_STATIC = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    mark_stale_running_as_interrupted()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="OSINT Toolkit Web", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(pages.router)
    app.include_router(api.router)
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")
    return app
