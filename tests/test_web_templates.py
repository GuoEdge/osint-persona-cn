"""Web template smoke tests."""

from __future__ import annotations

from pathlib import Path

TEMPLATES = Path(__file__).resolve().parents[1] / "src" / "osint_toolkit" / "web" / "templates"


def test_ingest_page_wires_init_ingest():
    html = (TEMPLATES / "ingest.html").read_text(encoding="utf-8")
    assert "initIngest()" in html
    assert "ingest-preflight" in html


def test_settings_page_wires_init_settings():
    html = (TEMPLATES / "settings.html").read_text(encoding="utf-8")
    assert "initSettings()" in html
    assert "btn-refresh-auth" in html
