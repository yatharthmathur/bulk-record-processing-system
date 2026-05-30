from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.application.services.retry import AsyncRetryExecutor, RetryPolicy
from app.application.use_cases.bulk_create_hospitals import BulkCreateHospitalsUseCase
from app.domain.exceptions import ExternalServiceError
from app.domain.models import (
    BatchSnapshot,
    BatchStatus,
    BulkCreateBatchJob,
    ExternalHospital,
    HospitalRow,
)
from app.infrastructure.repositories.in_memory_batch_repository import (
    InMemoryBatchRepository,
)


class FakeHospitalDirectoryGateway:
    def __init__(
        self,
        fail_rows: dict[int, int] | None = None,
        activation_failures: int = 0,
    ) -> None:
        self._remaining_row_failures: dict[int, int] = dict(fail_rows or {})
        self._remaining_activation_failures: int = activation_failures
        self.row_attempts: dict[int, int] = {}
        self.activation_attempts: int = 0
        self.activated_batches: list[UUID] = []

    async def create_hospital(
        self, hospital: HospitalRow, batch_id: UUID
    ) -> ExternalHospital:
        self.row_attempts[hospital.row] = self.row_attempts.get(hospital.row, 0) + 1
        if self._remaining_row_failures.get(hospital.row, 0) > 0:
            self._remaining_row_failures[hospital.row] -= 1
            raise ExternalServiceError(
                f"Row {hospital.row}: simulated upstream failure"
            )

        return ExternalHospital(
            id=100 + hospital.row,
            name=hospital.name,
            address=hospital.address,
            phone=hospital.phone,
            creation_batch_id=batch_id,
            active=False,
        )

    async def activate_batch(self, batch_id: UUID) -> None:
        self.activation_attempts += 1
        if self._remaining_activation_failures > 0:
            self._remaining_activation_failures -= 1
            raise ExternalServiceError("simulated activation failure")
        self.activated_batches.append(batch_id)


async def no_sleep(_: float) -> None:
    return None


async def seed_batch(
    repository: InMemoryBatchRepository,
    batch_id: UUID,
    hospitals_count: int,
) -> None:
    await repository.save(
        BatchSnapshot(
            batch_id=batch_id,
            total_hospitals=hospitals_count,
            processed_hospitals=0,
            failed_hospitals=0,
            batch_activated=False,
            status=BatchStatus.QUEUED,
        )
    )


@pytest.mark.asyncio
async def test_bulk_create_successfully_creates_and_activates_batch() -> None:
    gateway = FakeHospitalDirectoryGateway()
    repository = InMemoryBatchRepository()
    batch_id = uuid4()
    await seed_batch(repository, batch_id, hospitals_count=2)
    use_case = BulkCreateHospitalsUseCase(
        batch_repository=repository,
        hospital_directory_gateway=gateway,
        retry_executor=AsyncRetryExecutor(
            RetryPolicy(max_attempts=3),
            sleep_func=no_sleep,
        ),
        max_concurrent_requests=4,
    )

    snapshot = await use_case.execute(
        BulkCreateBatchJob(
            batch_id=batch_id,
            hospitals=(
                HospitalRow(
                    row=1,
                    name="General Hospital",
                    address="123 Main St",
                    phone="555-0101",
                ),
                HospitalRow(row=2, name="City Clinic", address="99 Elm St", phone=None),
            ),
        )
    )

    assert snapshot.total_hospitals == 2
    assert snapshot.processed_hospitals == 2
    assert snapshot.failed_hospitals == 0
    assert snapshot.batch_activated is True
    assert snapshot.status == BatchStatus.COMPLETED
    assert [hospital.status for hospital in snapshot.hospitals] == [
        "created_and_activated",
        "created_and_activated",
    ]
    assert [hospital.attempts for hospital in snapshot.hospitals] == [1, 1]
    assert gateway.activated_batches == [snapshot.batch_id]


@pytest.mark.asyncio
async def test_bulk_create_retries_failed_row_and_then_succeeds() -> None:
    gateway = FakeHospitalDirectoryGateway(fail_rows={1: 2})
    repository = InMemoryBatchRepository()
    batch_id = uuid4()
    await seed_batch(repository, batch_id, hospitals_count=1)
    use_case = BulkCreateHospitalsUseCase(
        batch_repository=repository,
        hospital_directory_gateway=gateway,
        retry_executor=AsyncRetryExecutor(
            RetryPolicy(max_attempts=3, initial_delay_seconds=0.01),
            sleep_func=no_sleep,
        ),
        max_concurrent_requests=2,
    )

    snapshot = await use_case.execute(
        BulkCreateBatchJob(
            batch_id=batch_id,
            hospitals=(
                HospitalRow(
                    row=1, name="General Hospital", address="123 Main St", phone=None
                ),
            ),
        )
    )

    assert snapshot.processed_hospitals == 1
    assert snapshot.failed_hospitals == 0
    assert snapshot.batch_activated is True
    assert snapshot.hospitals[0].status == "created_and_activated"
    assert snapshot.hospitals[0].attempts == 3
    assert gateway.row_attempts[1] == 3


@pytest.mark.asyncio
async def test_bulk_create_fails_after_max_attempts_and_does_not_activate() -> None:
    gateway = FakeHospitalDirectoryGateway(fail_rows={2: 3})
    repository = InMemoryBatchRepository()
    batch_id = uuid4()
    await seed_batch(repository, batch_id, hospitals_count=2)
    use_case = BulkCreateHospitalsUseCase(
        batch_repository=repository,
        hospital_directory_gateway=gateway,
        retry_executor=AsyncRetryExecutor(
            RetryPolicy(max_attempts=3, initial_delay_seconds=0.01),
            sleep_func=no_sleep,
        ),
        max_concurrent_requests=4,
    )

    snapshot = await use_case.execute(
        BulkCreateBatchJob(
            batch_id=batch_id,
            hospitals=(
                HospitalRow(
                    row=1, name="General Hospital", address="123 Main St", phone=None
                ),
                HospitalRow(row=2, name="City Clinic", address="99 Elm St", phone=None),
            ),
        )
    )

    assert snapshot.processed_hospitals == 1
    assert snapshot.failed_hospitals == 1
    assert snapshot.batch_activated is False
    assert snapshot.status == BatchStatus.PARTIAL_FAILURE
    assert gateway.activated_batches == []
    assert snapshot.hospitals[1].status == "failed"
    assert snapshot.hospitals[1].attempts == 3
    assert snapshot.hospitals[1].error is not None


@pytest.mark.asyncio
async def test_bulk_create_retries_activation_before_marking_failure() -> None:
    gateway = FakeHospitalDirectoryGateway(activation_failures=3)
    repository = InMemoryBatchRepository()
    batch_id = uuid4()
    await seed_batch(repository, batch_id, hospitals_count=1)
    use_case = BulkCreateHospitalsUseCase(
        batch_repository=repository,
        hospital_directory_gateway=gateway,
        retry_executor=AsyncRetryExecutor(
            RetryPolicy(max_attempts=3, initial_delay_seconds=0.01),
            sleep_func=no_sleep,
        ),
        max_concurrent_requests=4,
    )

    snapshot = await use_case.execute(
        BulkCreateBatchJob(
            batch_id=batch_id,
            hospitals=(
                HospitalRow(
                    row=1, name="General Hospital", address="123 Main St", phone=None
                ),
            ),
        )
    )

    assert snapshot.processed_hospitals == 1
    assert snapshot.failed_hospitals == 0
    assert snapshot.batch_activated is False
    assert snapshot.status == BatchStatus.ACTIVATION_FAILED
    assert snapshot.hospitals[0].status == "created_activation_failed"
    assert snapshot.hospitals[0].attempts == 3
    assert gateway.activation_attempts == 3
