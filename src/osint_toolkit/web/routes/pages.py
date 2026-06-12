"""页面路由 / Page routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from osint_toolkit.utils.config import load_config

_templates_dir = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))

router = APIRouter()


def _nav_context(active: str) -> dict:
    return {
        "nav_groups": [
            {
                "label": "采集",
                "links": [
                    {"id": "workspace", "label": "搜罗", "href": "/"},
                    {"id": "save", "label": "收录", "href": "/save"},
                ],
            },
            {
                "label": "沉淀",
                "links": [
                    {"id": "knowledge", "label": "知识库", "href": "/knowledge"},
                    {"id": "digest", "label": "简报", "href": "/digest"},
                ],
            },
            {
                "label": "画像",
                "links": [
                    {"id": "ingest", "label": "扩展与导入", "href": "/ingest"},
                    {"id": "behavior", "label": "行为时间线", "href": "/behavior"},
                    {"id": "persona", "label": "心智画像", "href": "/persona"},
                ],
            },
            {
                "label": "审计",
                "links": [
                    {"id": "runs", "label": "运行记录", "href": "/runs"},
                ],
            },
            {
                "label": "系统",
                "links": [
                    {"id": "ai", "label": "AI 控制", "href": "/ai"},
                    {"id": "settings", "label": "设置", "href": "/settings"},
                ],
            },
        ],
        "active": active,
        "profiles": list(load_config().get("profiles", {}).keys()),
        "sources": ["zhihu", "bilibili", "web", "v2ex", "rss"],
    }


@router.get("/", response_class=HTMLResponse)
async def page_workspace(request: Request) -> HTMLResponse:
    ctx = _nav_context("workspace")
    return templates.TemplateResponse(request, "workspace.html", ctx)


@router.get("/save", response_class=HTMLResponse)
async def page_save(request: Request, url: str = "") -> HTMLResponse:
    target = "/knowledge?tab=save"
    if url:
        target += f"&url={url}"
    return RedirectResponse(url=target, status_code=302)


@router.get("/knowledge", response_class=HTMLResponse)
async def page_knowledge(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "knowledge.html", _nav_context("knowledge"))


@router.get("/digest", response_class=HTMLResponse)
async def page_digest(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "digest.html", _nav_context("digest"))


@router.get("/persona", response_class=HTMLResponse)
async def page_persona(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "persona.html", _nav_context("persona"))


@router.get("/ingest", response_class=HTMLResponse)
async def page_ingest(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "ingest.html", _nav_context("ingest"))


@router.get("/behavior", response_class=HTMLResponse)
async def page_behavior(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "behavior.html", _nav_context("behavior"))


@router.get("/runs", response_class=HTMLResponse)
async def page_runs(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "runs.html", _nav_context("runs"))


@router.get("/runs/{run_id}", response_class=HTMLResponse)
async def page_run_detail(request: Request, run_id: str) -> HTMLResponse:
    ctx = _nav_context("runs")
    ctx["run_id"] = run_id
    return templates.TemplateResponse(request, "run_detail.html", ctx)


@router.get("/ai", response_class=HTMLResponse)
async def page_ai(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "ai.html", _nav_context("ai"))


@router.get("/settings", response_class=HTMLResponse)
async def page_settings(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "settings.html", _nav_context("settings"))
