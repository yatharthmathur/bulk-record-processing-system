from __future__ import annotations

import asyncio
from uuid import UUID

from typing_extensions import override

from app.application.ports.repositories import BatchRepository
from app.domain.models import BatchSnapshot


class InMemoryBatchRepository(BatchRepository):
    def __init__(self) -> None:
        self._items: dict[UUID, BatchSnapshot] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    @override
    async def save(self, snapshot: BatchSnapshot) -> None:
        async with self._lock:
            self._items[snapshot.batch_id] = snapshot

    @override
    async def get(self, batch_id: UUID) -> BatchSnapshot | None:
        async with self._lock:
            return self._items.get(batch_id)

    @override
    async def shutdown(self) -> None:
        return None
