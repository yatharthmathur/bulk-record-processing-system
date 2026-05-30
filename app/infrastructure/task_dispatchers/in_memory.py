from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from typing_extensions import override

from app.application.ports.task_dispatchers import BatchTaskDispatcher
from app.domain.models import BulkCreateBatchJob

logger = logging.getLogger(__name__)


class InMemoryBackgroundBatchTaskDispatcher(BatchTaskDispatcher):
    def __init__(
        self,
        handler: Callable[[BulkCreateBatchJob], Awaitable[None]],
    ) -> None:
        self._handler: Callable[[BulkCreateBatchJob], Awaitable[None]] = handler
        self._tasks: set[asyncio.Task[None]] = set()

    @override
    async def dispatch(self, job: BulkCreateBatchJob) -> None:
        task = asyncio.create_task(self._run(job), name=f"bulk-batch-{job.batch_id}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    @override
    async def shutdown(self) -> None:
        if not self._tasks:
            return
        _ = await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _run(self, job: BulkCreateBatchJob) -> None:
        try:
            await self._handler(job)
        except Exception:
            logger.exception(
                "Unhandled exception while processing batch %s", job.batch_id
            )


class InlineBatchTaskDispatcher(BatchTaskDispatcher):
    def __init__(
        self,
        handler: Callable[[BulkCreateBatchJob], Awaitable[None]],
    ) -> None:
        self._handler: Callable[[BulkCreateBatchJob], Awaitable[None]] = handler

    @override
    async def dispatch(self, job: BulkCreateBatchJob) -> None:
        await self._handler(job)

    @override
    async def shutdown(self) -> None:
        return None
