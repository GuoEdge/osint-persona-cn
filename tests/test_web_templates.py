"""Web template smoke tests."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "src" / "osint_toolkit" / "web" / "templates"
STATIC = ROOT / "src" / "osint_toolkit" / "web" / "static"


def test_ingest_page_wires_init_ingest():
    html = (TEMPLATES / "ingest.html").read_text(encoding="utf-8")
    assert "initIngest()" in html
    assert "ingest-preflight" in html
    assert 'id="full-sync-card"' in html
    assert html.count('id="extension"') == 1


def test_settings_page_wires_init_settings():
    html = (TEMPLATES / "settings.html").read_text(encoding="utf-8")
    assert "initSettings()" in html
    assert "btn-refresh-auth" in html
    assert "onboarding-callout" in html
    assert 'id="setup-wizard"' in html


def test_workspace_core_options_grouped():
    html = (TEMPLATES / "workspace.html").read_text(encoding="utf-8")
    assert "更多选项" in html
    assert "高级选项" in html
    assert 'id="setup-wizard"' in html


def test_app_js_product_polish_helpers():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "async function initWorkspaceContext()" in js
    assert "initResearchNoteForm();" in js
    assert "async function getShellStatus(" in js
    assert "产出文件" in js
    assert "alert(" not in js
