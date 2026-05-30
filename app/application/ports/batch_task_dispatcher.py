from __future__ import annotations

from typing import Protocol

from app.domain.models import BulkCreateBatchJob


class BatchTaskDispatcher(Protocol):
    async def dispatch(self, job: BulkCreateBatchJob) -> None: ...

    async def shutdown(self) -> None: ...
