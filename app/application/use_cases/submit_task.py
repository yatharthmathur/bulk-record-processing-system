from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

from app.application.ports.repositories import BatchRepository
from app.application.ports.task_dispatchers import BatchTaskDispatcher
from app.application.services.csv_parser import HospitalCsvParser
from app.domain.models import BatchSnapshot, BatchStatus, BulkCreateBatchJob


class SubmitBulkCreateTaskUseCase:
    def __init__(
        self,
        batch_repository: BatchRepository,
        batch_task_dispatcher: BatchTaskDispatcher,
        csv_parser: HospitalCsvParser,
    ) -> None:
        self._batch_repository: BatchRepository = batch_repository
        self._batch_task_dispatcher: BatchTaskDispatcher = batch_task_dispatcher
        self._csv_parser: HospitalCsvParser = csv_parser

    async def execute(self, raw_csv: bytes) -> BatchSnapshot:
        hospitals = self._csv_parser.parse(raw_csv)
        batch_id = uuid4()
        file_md5 = hashlib.md5(raw_csv, usedforsecurity=False).hexdigest()

        existing_batch_id = await self._batch_repository.claim_in_flight_file_md5(
            file_md5, batch_id
        )
        if existing_batch_id is not None:
            existing_snapshot = await self._batch_repository.get(existing_batch_id)
            if existing_snapshot is not None:
                return existing_snapshot

        snapshot = BatchSnapshot(
            batch_id=batch_id,
            total_hospitals=len(hospitals),
            processed_hospitals=0,
            failed_hospitals=0,
            batch_activated=False,
            status=BatchStatus.QUEUED,
            hospitals=tuple(),
            started_at=datetime.now(UTC),
            file_md5=file_md5,
        )
        await self._batch_repository.save(snapshot)
        job = BulkCreateBatchJob(batch_id=snapshot.batch_id, hospitals=tuple(hospitals))
        await self._batch_task_dispatcher.dispatch(job)
        return snapshot
