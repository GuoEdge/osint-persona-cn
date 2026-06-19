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
    assert "theme-appearance-control" in html
    assert 'id="appearance"' in html


def test_base_theme_bootstrap():
    html = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    assert "theme-init.js" in html
    assert "tokens.css" in html
    assert "ui.css" in html
    assert "initTheme()" in html
    assert "mobile-tab-bar" in html


def test_workspace_core_options_grouped():
    html = (TEMPLATES / "workspace.html").read_text(encoding="utf-8")
    assert "更多选项" in html
    assert "高级选项" in html
    assert "评论与社区层挖掘" in html
    assert 'id="setup-wizard"' in html
    assert 'id="research-suggested-queries"' in html
    assert "workspace-split-view" in html
    assert "report-reading-toolbar" in html
    assert "reading-surface" in html
    assert "ui-segmented" in html
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "function initTheme(" in js
    assert "function initReadingToolbar(" in js
    assert "function initGlobalShortcuts(" in js


def test_digest_reading_surface():
    html = (TEMPLATES / "digest.html").read_text(encoding="utf-8")
    assert "reading-surface" in html
    assert "ui-inset-group" in html
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "function ensureReadingSurface(" in js


def test_theme_init_script():
    script = (STATIC / "theme-init.js").read_text(encoding="utf-8")
    assert "osint-theme" in script
    assert "dataset.theme" in script


def test_ingest_inset_groups():
    html = (TEMPLATES / "ingest.html").read_text(encoding="utf-8")
    assert "ui-inset-group" in html
    assert 'id="full-sync-card"' in html


def test_theme_tokens_dark_surface_elevated():
    tokens = (STATIC / "tokens.css").read_text(encoding="utf-8")
    assert "--surface-elevated" in tokens
    assert '[data-theme="dark"]' in tokens
    assert "--semantic-info-fg" in tokens
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    assert "var(--surface-elevated, #f8fafc)" not in css
    assert "var(--surface-elevated, #f3f4f6)" not in css


def test_vivid_design_markers():
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    workspace = (TEMPLATES / "workspace.html").read_text(encoding="utf-8")
    tokens = (STATIC / "tokens.css").read_text(encoding="utf-8")
    ui = (STATIC / "ui.css").read_text(encoding="utf-8")
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "brand-mark" in base
    assert "pipeline-stepper" in workspace
    assert "empty-state-rich" in workspace
    assert "page-header--accent" in workspace
    assert "--hero-mesh" in tokens
    assert "--progress-shine" in tokens
    assert "prefers-reduced-motion" in ui
    assert "function renderEmptyStateRich(" in js


def test_source_auth_modal_markup():
    html = (TEMPLATES / "workspace.html").read_text(encoding="utf-8")
    assert 'id="source-auth-modal"' in html
    assert "source-auth-modal-inner" in html
    ui = (STATIC / "ui.css").read_text(encoding="utf-8")
    assert ".source-auth-modal" in ui
    assert "margin: auto" in ui


def test_overlay_feedback_styles():
    ui = (STATIC / "ui.css").read_text(encoding="utf-8")
    app = (STATIC / "app.css").read_text(encoding="utf-8")
    assert ".toast-warn" in ui
    assert "--semantic-success-bg" in ui
    assert "margin: auto" in ui
    assert "dialog {" in ui
    assert "#1e1e2e" not in app
    assert "#cdd6f4" not in app


def test_ai_page_tab_a11y():
    html = (TEMPLATES / "ai.html").read_text(encoding="utf-8")
    assert 'role="tablist"' in html
    assert 'aria-controls="panel-directives"' in html
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "async function initWorkspaceContext()" in js
    assert "initResearchNoteForm();" in js
    assert "void loadSuggestedQueries();" in js
    assert "async function getShellStatus(" in js
    assert "产出文件" in js
    assert "alert(" not in js
