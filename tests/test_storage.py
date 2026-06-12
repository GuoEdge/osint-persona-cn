"""存储测试."""

from osint_toolkit.models.intel_item import IntelItem
from osint_toolkit.storage.knowledge import recall, save_item


def test_save_and_recall(tmp_path, monkeypatch):
    monkeypatch.setattr("osint_toolkit.storage.sqlite.get_db_path", lambda: tmp_path / "knowledge.db")
    item = IntelItem(
        source="zhihu",
        type="answer",
        url="https://zhihu.com/q/1",
        title="测试 MCP 情报",
        content="MCP 协议相关内容",
    )
    save_item(item)
    found = recall("MCP")
    assert len(found) == 1
    assert found[0].title == item.title
