"""探测 AICU 是否可用 / Probe AICU availability."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from osint_toolkit.ingest.aicu import probe_aicu


def main() -> None:
    result = asyncio.run(probe_aicu())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    status = str(result.get("status", "FAIL"))
    if status == "PASS":
        raise SystemExit(0)
    if status in {"DISABLE", "WAF_BLOCKED"}:
        raise SystemExit(2)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
