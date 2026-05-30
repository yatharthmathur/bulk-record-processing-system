from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.application.services.csv_parser import HospitalCsvParser
from app.application.use_cases.submit_task import SubmitBulkCreateTaskUseCase
from app.domain.models import BatchSnapshot, BatchStatus, BulkCreateBatchJob
from app.infrastructure.repositories.in_memory import InMemoryBatchRepository


class FakeBatchTaskDispatcher:
    def __init__(self) -> None:
        self.jobs: list[BulkCreateBatchJob] = []

    async def dispatch(self, job: BulkCreateBatchJob) -> None:
        self.jobs.append(job)

    async def shutdown(self) -> None:
        return None


RAW_CSV = b"name,address\nGeneral Hospital,123 Main St\nCity Clinic,99 Elm St\n"


def build_submit_use_case(
    repository: InMemoryBatchRepository | None = None,
    dispatcher: FakeBatchTaskDispatcher | None = None,
) -> tuple[
    SubmitBulkCreateTaskUseCase, InMemoryBatchRepository, FakeBatchTaskDispatcher
]:
    repo = repository or InMemoryBatchRepository()
    disp = dispatcher or FakeBatchTaskDispatcher()
    use_case = SubmitBulkCreateTaskUseCase(
        batch_repository=repo,
        batch_task_dispatcher=disp,
        csv_parser=HospitalCsvParser(max_hospitals=20),
    )
    return use_case, repo, disp


@pytest.mark.asyncio
async def test_submit_bulk_create_persists_queued_batch_and_dispatches_job() -> None:
    use_case, repository, dispatcher = build_submit_use_case()

    snapshot = await use_case.execute(RAW_CSV)

    assert snapshot.status == BatchStatus.QUEUED
    assert snapshot.processed_hospitals == 0
    assert snapshot.failed_hospitals == 0
    assert snapshot.file_md5 is not None
    assert len(dispatcher.jobs) == 1
    assert dispatcher.jobs[0].batch_id == snapshot.batch_id
    assert len(dispatcher.jobs[0].hospitals) == 2

    stored_snapshot = await repository.get(snapshot.batch_id)
    assert stored_snapshot is not None
    assert stored_snapshot.status == BatchStatus.QUEUED


@pytest.mark.asyncio
async def test_submit_deduplicates_in_flight_uploads_by_file_md5() -> None:
    use_case, _, dispatcher = build_submit_use_case()

    first = await use_case.execute(RAW_CSV)
    second = await use_case.execute(RAW_CSV)

    assert second.batch_id == first.batch_id
    assert len(dispatcher.jobs) == 1


@pytest.mark.asyncio
async def test_submit_allows_resubmit_after_terminal_batch_released() -> None:
    use_case, repository, dispatcher = build_submit_use_case()

    first = await use_case.execute(RAW_CSV)
    await repository.save(
        BatchSnapshot(
            batch_id=first.batch_id,
            total_hospitals=first.total_hospitals,
            processed_hospitals=first.total_hospitals,
            failed_hospitals=0,
            batch_activated=True,
            status=BatchStatus.COMPLETED,
            started_at=first.started_at,
            completed_at=datetime.now(UTC),
            file_md5=first.file_md5,
        )
    )
    assert first.file_md5 is not None
    await repository.release_file_md5(first.file_md5, first.batch_id)

    second = await use_case.execute(RAW_CSV)

    assert second.batch_id != first.batch_id
    assert len(dispatcher.jobs) == 2


@pytest.mark.asyncio
async def test_concurrent_submits_with_same_file_resolve_to_one_batch() -> None:
    use_case, _, dispatcher = build_submit_use_case()

    snapshots = await asyncio.gather(
        *[use_case.execute(RAW_CSV) for _ in range(5)],
    )

    assert len({snapshot.batch_id for snapshot in snapshots}) == 1
    assert len(dispatcher.jobs) == 1


@pytest.mark.asyncio
async def test_in_memory_repository_claim_and_release_semantics() -> None:
    repository = InMemoryBatchRepository()
    file_md5 = "abc123"
    first_batch_id = uuid4()
    second_batch_id = uuid4()

    assert await repository.claim_in_flight_file_md5(file_md5, first_batch_id) is None
    assert (
        await repository.claim_in_flight_file_md5(file_md5, second_batch_id)
        == first_batch_id
    )

    await repository.save(
        BatchSnapshot(
            batch_id=first_batch_id,
            total_hospitals=1,
            processed_hospitals=1,
            failed_hospitals=0,
            batch_activated=True,
            status=BatchStatus.COMPLETED,
            file_md5=file_md5,
        )
    )
    await repository.release_file_md5(file_md5, first_batch_id)

    assert await repository.claim_in_flight_file_md5(file_md5, second_batch_id) is None
