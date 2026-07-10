from __future__ import annotations

import json

from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.storage.knowledge import save_item
from osint_toolkit.storage.sqlite import connect
from osint_toolkit.utils.config import reset_config_cache


def _cloud_cfg(vault_path: str, *, sync_mode: str = "passive", provider: str = "local_folder") -> dict:
    return {
        "knowledge": {
            "cloud": {
                "enabled": True,
                "provider": provider,
                "vault_path": vault_path,
                "sync_mode": sync_mode,
                "include_attachments": True,
                "include_raw_archives": False,
            }
        }
    }


def test_sync_item_to_cloud_writes_markdown_and_state(tmp_path, monkeypatch):
    from osint_toolkit.services import cloud

    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: tmp_path / "knowledge.db")
    monkeypatch.setattr(cloud, "load_config", lambda: _cloud_cfg(str(tmp_path / "vault")))
    reset_config_cache()

    item = IntelItem(
        id="item-1",
        source="web",
        type="article",
        url="https://example.test/1",
        title="知识条目",
        content="正文内容",
        summary="摘要",
        topics=["MCP"],
        personal={
            "concepts": ["本地知识库"],
            "claims": ["Markdown vault 是长期资产"],
            "questions": ["如何从 vault 重建索引？"],
            "project": "知识核心",
            "relations": [{"relation": "explains", "to": "本地知识库", "evidence": "摘要"}],
            "confidence": 0.8,
            "evidence_refs": ["https://example.test/1"],
        },
    )
    save_item(item)

    result = cloud.sync_item_to_cloud(item, capture_reason="manual_save")

    assert result["status"] == "synced"
    note_path = tmp_path / "vault" / result["vault_path"]
    assert note_path.exists()
    text = note_path.read_text(encoding="utf-8")
    assert "capture_reason: manual_save" in text
    assert "concepts:" in text
    assert "本地知识库" in text
    assert "project: 知识核心" in text
    assert "## 正文" in text

    conn = connect()
    try:
        row = conn.execute("SELECT status, vault_path FROM vault_sync_state WHERE item_id = ?", ("item-1",)).fetchone()
    finally:
        conn.close()
    assert row["status"] == "synced"
    assert row["vault_path"] == result["vault_path"]


def test_sync_item_to_cloud_creates_conflict_copy_for_user_edit(tmp_path, monkeypatch):
    from osint_toolkit.services import cloud

    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: tmp_path / "knowledge.db")
    monkeypatch.setattr(cloud, "load_config", lambda: _cloud_cfg(str(tmp_path / "vault")))
    reset_config_cache()

    item = IntelItem(
        id="item-2",
        source="web",
        type="article",
        url="https://example.test/2",
        title="会冲突的条目",
        content="正文 A",
        summary="摘要 A",
    )
    save_item(item)
    first = cloud.sync_item_to_cloud(item, capture_reason="manual_save")
    note_path = tmp_path / "vault" / first["vault_path"]

    text = note_path.read_text(encoding="utf-8")
    note_path.write_text(text + "\n用户手改了一段内容\n", encoding="utf-8")

    item.content = "正文 B"
    item.summary = "摘要 B"
    second = cloud.sync_item_to_cloud(item, capture_reason="manual_save")

    assert second["status"] == "conflict"
    assert second["conflict"]["conflict_path"].endswith(".md")
    conflict_path = tmp_path / "vault" / second["conflict"]["conflict_path"]
    assert conflict_path.exists()
    conflicts = cloud.list_cloud_conflicts()
    assert conflicts[0]["item_id"] == "item-2"


def test_init_cloud_writes_config_and_layout(tmp_path, monkeypatch):
    from osint_toolkit.services import cloud

    written: dict = {}

    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(cloud, "get_data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(cloud, "load_config", lambda: {"knowledge": {"cloud": {"enabled": True}}})
    monkeypatch.setattr(
        cloud,
        "save_user_config_patch",
        lambda patch: (written.update(patch), str(tmp_path / "data" / "config.yaml"))[1],
    )
    reset_config_cache()

    result = cloud.init_cloud(provider="local_folder", vault_path=str(tmp_path / "vault"), sync_mode="passive")

    assert result["ok"] is True
    assert (tmp_path / "vault" / "Inbox").exists()
    assert written["knowledge"]["cloud"]["vault_path"] == str((tmp_path / "vault").resolve())
    assert written["knowledge"]["cloud"]["provider"] == "local_folder"
    assert written["knowledge"]["cloud"]["sync_mode"] == "passive"


def test_init_cloud_supports_selected_onedrive_root_and_name(tmp_path, monkeypatch):
    from osint_toolkit.services import cloud

    one_a = tmp_path / "OneDrive-A"
    one_b = tmp_path / "OneDrive-B"
    one_a.mkdir()
    one_b.mkdir()
    written: dict = {}

    monkeypatch.setattr("osint_toolkit.auth.paths.get_data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(cloud, "get_data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(cloud, "_detect_onedrive_candidates", lambda: [one_a, one_b])
    monkeypatch.setattr(cloud, "load_config", lambda: {"knowledge": {"cloud": {"enabled": True}}})
    monkeypatch.setattr(
        cloud,
        "save_user_config_patch",
        lambda patch: (written.update(patch), str(tmp_path / "data" / "config.yaml"))[1],
    )
    reset_config_cache()

    result = cloud.init_cloud(
        provider="onedrive_folder",
        onedrive_root=str(one_b),
        vault_name="Research Vault",
        sync_mode="manual",
    )

    assert result["vault_path"] == str((one_b / "Research-Vault").resolve())
    assert written["knowledge"]["cloud"]["vault_path"] == str((one_b / "Research-Vault").resolve())
    assert written["knowledge"]["cloud"]["sync_mode"] == "manual"


def test_sync_item_to_cloud_queues_when_manual_until_full_sync(tmp_path, monkeypatch):
    from osint_toolkit.services import cloud

    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: tmp_path / "knowledge.db")
    monkeypatch.setattr(cloud, "load_config", lambda: _cloud_cfg(str(tmp_path / "vault"), sync_mode="manual"))
    reset_config_cache()

    item = IntelItem(
        id="queued-1",
        source="web",
        type="article",
        url="https://example.test/q1",
        title="待同步条目",
        content="正文内容",
        summary="摘要",
    )
    save_item(item)

    queued = cloud.sync_item_to_cloud(item, capture_reason="manual_save")

    assert queued["status"] == "pending"
    assert not (tmp_path / "vault" / queued["vault_path"]).exists()

    synced = cloud.sync_cloud()

    assert synced["synced_items"] == 1
    assert (tmp_path / "vault" / queued["vault_path"]).exists()

    conn = connect()
    try:
        row = conn.execute("SELECT status FROM vault_sync_state WHERE item_id = ?", ("queued-1",)).fetchone()
    finally:
        conn.close()
    assert row["status"] == "synced"


def test_reindex_cloud_restores_items_and_links(tmp_path, monkeypatch):
    from osint_toolkit.services import cloud, knowledge

    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: tmp_path / "knowledge.db")
    monkeypatch.setattr(cloud, "load_config", lambda: _cloud_cfg(str(tmp_path / "vault")))
    reset_config_cache()

    item_a = IntelItem(
        id="item-a",
        source="web",
        type="article",
        url="https://example.test/a",
        title="A",
        content="alpha",
        summary="A summary",
        topics=["shared"],
    )
    item_b = IntelItem(
        id="item-b",
        source="web",
        type="article",
        url="https://example.test/b",
        title="B",
        content="beta",
        summary="B summary",
        topics=["shared"],
    )
    item_a.personal["entities"] = ["entity-1"]
    item_b.personal["entities"] = ["entity-1"]
    save_item(item_a)
    save_item(item_b)
    cloud.sync_item_to_cloud(item_a, capture_reason="manual_save")
    cloud.sync_item_to_cloud(item_b, capture_reason="manual_save")
    cloud.refresh_cloud_indexes()

    conn = connect()
    try:
        conn.execute("DELETE FROM intel_fts")
        conn.execute("DELETE FROM intel_items")
        conn.execute("DELETE FROM knowledge_links")
        conn.execute("DELETE FROM vault_sync_state")
        conn.commit()
    finally:
        conn.close()

    result = cloud.reindex_cloud()
    assert result["reindexed_items"] == 2
    assert knowledge.count_items() == 2

    conn = connect()
    try:
        row = conn.execute("SELECT COUNT(*) AS c FROM knowledge_links").fetchone()
    finally:
        conn.close()
    assert int(row["c"]) >= 1

    sync_state = json.loads((tmp_path / "vault" / "_osint" / "sync-state.json").read_text(encoding="utf-8"))
    assert sync_state["item_count"] == 2

    graph = json.loads((tmp_path / "vault" / "_osint" / "graph.json").read_text(encoding="utf-8"))
    assert graph["nodes"]
    assert graph["edges"]
    expected = {"same_topic", "same_entity", "mentions_entity", "explains"}
    assert any(edge["relation"] in expected for edge in graph["edges"])


def test_reindex_cloud_prunes_stale_synced_items(tmp_path, monkeypatch):
    from osint_toolkit.services import cloud, knowledge

    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: tmp_path / "knowledge.db")
    monkeypatch.setattr(cloud, "load_config", lambda: _cloud_cfg(str(tmp_path / "vault")))
    reset_config_cache()

    item = IntelItem(
        id="stale-item",
        source="web",
        type="article",
        url="https://example.test/stale",
        title="会被移除",
        content="stale",
    )
    save_item(item)
    result = cloud.sync_item_to_cloud(item, capture_reason="manual_save")
    note_path = tmp_path / "vault" / result["vault_path"]
    note_path.unlink()

    reindexed = cloud.reindex_cloud()

    assert reindexed["pruned_items"] == 1
    assert knowledge.count_items() == 0


def test_cloud_status_reports_onedrive_health(tmp_path, monkeypatch):
    from osint_toolkit.services import cloud

    onedrive_root = tmp_path / "OneDrive"
    vault_root = onedrive_root / "OSINT-Knowledge"
    vault_root.mkdir(parents=True)
    monkeypatch.setattr(cloud, "load_config", lambda: {
        "knowledge": {
            "cloud": {
                "enabled": True,
                "provider": "onedrive_folder",
                "vault_path": str(vault_root),
                "sync_mode": "scheduled",
                "include_attachments": True,
                "include_raw_archives": False,
            }
        }
    })
    monkeypatch.setattr(cloud, "_detect_onedrive_candidates", lambda: [onedrive_root])
    reset_config_cache()

    status = cloud.get_cloud_status()

    assert status["ready"] is True
    assert status["is_onedrive_vault"] is True
    assert status["matched_onedrive_root"] == str(onedrive_root)
    assert "scheduled 模式当前先进入待同步队列" in " ".join(status["health"]["warnings"])
