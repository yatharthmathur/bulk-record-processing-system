from __future__ import annotations

from typing import TypedDict, cast
from uuid import UUID

from fastapi.testclient import TestClient

from app.application.services.csv_parser import CsvHospitalParser
from app.application.services.retry import AsyncRetryExecutor, RetryPolicy
from app.application.use_cases.bulk_create_hospitals import BulkCreateHospitalsUseCase
from app.application.use_cases.get_batch_status import GetBatchStatusUseCase
from app.application.use_cases.submit_bulk_create_hospitals import (
    SubmitBulkCreateHospitalsUseCase,
)
from app.bootstrap import AppContainer
from app.domain.models import BulkCreateBatchJob, ExternalHospital, HospitalRow
from app.infrastructure.repositories.in_memory_batch_repository import (
    InMemoryBatchRepository,
)
from app.infrastructure.settings import Settings
from app.infrastructure.task_dispatchers.in_memory import InlineBatchTaskDispatcher
from app.main import create_app


class QueuedBatchResponse(TypedDict):
    batch_id: str
    total_hospitals: int
    processed_hospitals: int
    failed_hospitals: int
    batch_activated: bool
    status: str


class CompletedHospitalResponse(TypedDict):
    status: str
    attempts: int


class CompletedBatchResponse(QueuedBatchResponse):
    hospitals: list[CompletedHospitalResponse]


class FakeHospitalDirectoryGateway:
    async def create_hospital(
        self, hospital: HospitalRow, batch_id: UUID
    ) -> ExternalHospital:
        return ExternalHospital(
            id=200 + hospital.row,
            name=hospital.name,
            address=hospital.address,
            phone=hospital.phone,
            creation_batch_id=batch_id,
            active=False,
        )

    async def activate_batch(self, batch_id: UUID) -> None:
        _ = batch_id
        return None


async def no_sleep(_: float) -> None:
    return None


def build_test_client() -> TestClient:
    settings = Settings(batch_task_backend="in_memory")
    repository = InMemoryBatchRepository()
    gateway = FakeHospitalDirectoryGateway()
    parser = CsvHospitalParser(max_hospitals=settings.max_csv_hospitals)
    processor = BulkCreateHospitalsUseCase(
        batch_repository=repository,
        hospital_directory_gateway=gateway,
        retry_executor=AsyncRetryExecutor(
            RetryPolicy(max_attempts=3), sleep_func=no_sleep
        ),
        max_concurrent_requests=2,
    )

    async def process_job(job: BulkCreateBatchJob) -> None:
        _ = await processor.execute(job)

    dispatcher = InlineBatchTaskDispatcher(process_job)
    container = AppContainer(
        settings=settings,
        batch_repository=repository,
        batch_task_dispatcher=dispatcher,
        hospital_directory_gateway=gateway,
        submit_bulk_create_hospitals_use_case=SubmitBulkCreateHospitalsUseCase(
            batch_repository=repository,
            batch_task_dispatcher=dispatcher,
            csv_parser=parser,
        ),
        bulk_create_hospitals_use_case=processor,
        get_batch_status_use_case=GetBatchStatusUseCase(batch_repository=repository),
    )
    return TestClient(create_app(container))


def test_bulk_create_endpoint_returns_queued_batch_and_status_can_be_polled() -> None:
    with build_test_client() as client:
        response = client.post(
            "/hospitals/bulk",
            files={
                "file": (
                    "hospitals.csv",
                    b"name,address,phone\nGeneral Hospital,123 Main St,555-0101\n",
                    "text/csv",
                )
            },
        )

        assert response.status_code == 202
        payload = cast(QueuedBatchResponse, response.json())
        assert payload["total_hospitals"] == 1
        assert payload["processed_hospitals"] == 0
        assert payload["failed_hospitals"] == 0
        assert payload["batch_activated"] is False
        assert payload["status"] == "queued"

        batch_response = client.get(f"/batches/{payload['batch_id']}")
        assert batch_response.status_code == 200
        batch_payload = cast(CompletedBatchResponse, batch_response.json())
        assert batch_payload["batch_id"] == payload["batch_id"]
        assert batch_payload["status"] == "completed"
        assert batch_payload["processed_hospitals"] == 1
        assert batch_payload["batch_activated"] is True
        assert batch_payload["hospitals"][0]["status"] == "created_and_activated"
        assert batch_payload["hospitals"][0]["attempts"] == 1


def test_bulk_create_endpoint_rejects_invalid_csv() -> None:
    with build_test_client() as client:
        response = client.post(
            "/hospitals/bulk",
            files={
                "file": (
                    "bad.csv",
                    b"hospital_name,address\nGeneral Hospital,123 Main St\n",
                    "text/csv",
                )
            },
        )

        assert response.status_code == 422
        assert "CSV headers must be exactly" in response.json()["detail"][0]
