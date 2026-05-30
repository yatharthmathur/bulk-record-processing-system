from __future__ import annotations

import asyncio
from uuid import UUID

from typing_extensions import override

from app.application.ports.repositories import BatchRepository
from app.domain.models import BatchSnapshot


class InMemoryBatchRepository(BatchRepository):
    def __init__(self) -> None:
        self._items: dict[UUID, BatchSnapshot] = {}
        self._in_flight_md5: dict[str, UUID] = {}
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
    async def claim_in_flight_file_md5(
        self, file_md5: str, batch_id: UUID
    ) -> UUID | None:
        async with self._lock:
            existing_batch_id = self._in_flight_md5.get(file_md5)
            if existing_batch_id is not None and existing_batch_id != batch_id:
                existing_snapshot = self._items.get(existing_batch_id)
                if existing_snapshot is None or not existing_snapshot.is_finished:
                    return existing_batch_id

            self._in_flight_md5[file_md5] = batch_id
            return None

    @override
    async def release_file_md5(self, file_md5: str, batch_id: UUID) -> None:
        async with self._lock:
            if self._in_flight_md5.get(file_md5) == batch_id:
                del self._in_flight_md5[file_md5]

    @override
    async def shutdown(self) -> None:
        return None
