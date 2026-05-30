from __future__ import annotations

import pytest

from app.application.services.csv_parser import HospitalCsvParser
from app.application.use_cases.submit_task import (
    SubmitBulkCreateTaskUseCase,
)
from app.domain.models import BatchStatus, BulkCreateBatchJob
from app.infrastructure.repositories.in_memory import (
    InMemoryBatchRepository,
)


class FakeBatchTaskDispatcher:
    def __init__(self) -> None:
        self.jobs: list[BulkCreateBatchJob] = []

    async def dispatch(self, job: BulkCreateBatchJob) -> None:
        self.jobs.append(job)

    async def shutdown(self) -> None:
        return None


@pytest.mark.asyncio
async def test_submit_bulk_create_persists_queued_batch_and_dispatches_job() -> None:
    repository = InMemoryBatchRepository()
    dispatcher = FakeBatchTaskDispatcher()
    use_case = SubmitBulkCreateTaskUseCase(
        batch_repository=repository,
        batch_task_dispatcher=dispatcher,
        csv_parser=HospitalCsvParser(max_hospitals=20),
    )

    snapshot = await use_case.execute(
        b"name,address\nGeneral Hospital,123 Main St\nCity Clinic,99 Elm St\n"
    )

    assert snapshot.status == BatchStatus.QUEUED
    assert snapshot.processed_hospitals == 0
    assert snapshot.failed_hospitals == 0
    assert len(dispatcher.jobs) == 1
    assert dispatcher.jobs[0].batch_id == snapshot.batch_id
    assert len(dispatcher.jobs[0].hospitals) == 2

    stored_snapshot = await repository.get(snapshot.batch_id)
    assert stored_snapshot is not None
    assert stored_snapshot.status == BatchStatus.QUEUED
