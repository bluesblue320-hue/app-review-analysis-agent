"""Application lifespan tasks."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from backend.services.dataset_service import dataset_store
from backend.services.insight_store import insight_store

logger = logging.getLogger(__name__)


def cleanup_expired_records() -> int:
    datasets = int(dataset_store.cleanup_expired())
    insights = int(insight_store.cleanup_expired())
    if datasets or insights:
        logger.info(
            "Expired records removed: datasets=%s insights=%s",
            datasets,
            insights,
        )
    return datasets + insights


async def _cleanup_loop() -> None:
    while True:
        await asyncio.sleep(3600)
        try:
            cleanup_expired_records()
        except Exception as exc:
            logger.warning(
                "Expired record cleanup failed: error_type=%s",
                type(exc).__name__,
            )


@asynccontextmanager
async def application_lifespan(_application):
    cleanup_expired_records()
    task = asyncio.create_task(_cleanup_loop())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
