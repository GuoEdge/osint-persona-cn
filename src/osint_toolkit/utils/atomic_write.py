"""原子写文件 / Atomic file write helper."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """先写临时文件再 os.replace 原子替换，避免半写文件被读到。

    与 ``Path.write_text(text, encoding="utf-8")`` 对纯 ``\\n`` 内容字节一致
    （``newline=""`` 不做 CRLF 翻译）。父目录不存在时自动创建。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as f:
            f.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
