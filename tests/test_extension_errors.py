"""Extension auto-save error reporting tests."""

from __future__ import annotations

import pytest

from osint_toolkit.services import extension as ext_service


@pytest.mark.asyncio
async def test_auto_save_errors_returned(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path)
    db = tmp_path / "knowledge.db"
    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: db)

    async def fail_save(url, **kwargs):
        raise RuntimeError("collector down")

    monkeypatch.setattr("osint_toolkit.services.save.save_url", fail_save)

    result = await ext_service.ingest_extension_batch(
        [
            {
                "kind": "save_to_osint",
                "url": "https://www.bilibili.com/video/BV1xx411c7mD",
                "save_knowledge": True,
                "title": "test",
            }
        ]
    )
    assert result.get("warnings") or result.get("auto_save_errors")
