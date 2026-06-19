"""后台监视调度 / Background watch scheduler."""

from __future__ import annotations

import asyncio
import logging

from osint_toolkit.services.watch import run_due_watches

logger = logging.getLogger(__name__)

_CHECK_INTERVAL_SEC = 30 * 60


async def watch_scheduler_loop() -> None:
    while True:
        try:
            results = await run_due_watches()
            for row in results:
                if row.get("ok"):
                    logger.info(
                        "watch %s done: %s new URLs (run %s)",
                        row.get("watch_id"),
                        row.get("new_count"),
                        row.get("run_id"),
                    )
                else:
                    logger.warning("watch %s failed: %s", row.get("watch_id"), row.get("error"))
        except Exception:  # noqa: BLE001
            logger.exception("watch scheduler tick failed")
        await asyncio.sleep(_CHECK_INTERVAL_SEC)
