from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.application.ports.batch_repository import BatchRepository
from app.application.ports.batch_task_dispatcher import BatchTaskDispatcher
from app.application.services.csv_parser import CsvHospitalParser
from app.domain.models import BatchSnapshot, BatchStatus, BulkCreateBatchJob


class SubmitBulkCreateHospitalsUseCase:
    def __init__(
        self,
        batch_repository: BatchRepository,
        batch_task_dispatcher: BatchTaskDispatcher,
        csv_parser: CsvHospitalParser,
    ) -> None:
        self._batch_repository: BatchRepository = batch_repository
        self._batch_task_dispatcher: BatchTaskDispatcher = batch_task_dispatcher
        self._csv_parser: CsvHospitalParser = csv_parser

    async def execute(self, raw_csv: bytes) -> BatchSnapshot:
        hospitals = self._csv_parser.parse(raw_csv)
        snapshot = BatchSnapshot(
            batch_id=uuid4(),
            total_hospitals=len(hospitals),
            processed_hospitals=0,
            failed_hospitals=0,
            batch_activated=False,
            status=BatchStatus.QUEUED,
            hospitals=tuple(),
            started_at=datetime.now(UTC),
        )
        await self._batch_repository.save(snapshot)
        job = BulkCreateBatchJob(batch_id=snapshot.batch_id, hospitals=tuple(hospitals))
        await self._batch_task_dispatcher.dispatch(job)
        return snapshot
