from __future__ import annotations

from uuid import UUID

from app.application.ports.repositories import BatchRepository
from app.domain.exceptions import BatchNotFoundError
from app.domain.models import BatchSnapshot


class GetBatchStatusUseCase:
    def __init__(self, batch_repository: BatchRepository) -> None:
        self._batch_repository: BatchRepository = batch_repository

    async def execute(self, batch_id: UUID) -> BatchSnapshot:
        snapshot = await self._batch_repository.get(batch_id)
        if snapshot is None:
            raise BatchNotFoundError(str(batch_id))
        return snapshot
