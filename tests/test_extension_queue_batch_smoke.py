"""Smoke test: extension queue batch size stays at 25 (pitfall #16 guard)."""

from __future__ import annotations

import re
from pathlib import Path


def test_extension_queue_batch_size_is_25():
    text = Path("extension/lib/queue.js").read_text(encoding="utf-8")
    m = re.search(r"_batchSize:\s*(\d+)", text)
    assert m, "_batchSize not found in queue.js"
    assert int(m.group(1)) == 25, f"_batchSize should be 25, got {m.group(1)}"


def test_extension_queue_flush_serialized():
    text = Path("extension/lib/queue.js").read_text(encoding="utf-8")
    assert "_flushChain" in text, "flush should be serialized via _flushChain"
    assert "async _doFlush()" in text, "flush body should be renamed to _doFlush"
