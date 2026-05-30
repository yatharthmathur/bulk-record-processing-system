from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx

from app.application.ports.batch_repository import BatchRepository
from app.application.ports.batch_task_dispatcher import BatchTaskDispatcher
from app.application.ports.hospital_directory_gateway import HospitalDirectoryGateway
from app.application.services.csv_parser import CsvHospitalParser
from app.application.services.retry import AsyncRetryExecutor, RetryPolicy
from app.application.use_cases.bulk_create_hospitals import BulkCreateHospitalsUseCase
from app.application.use_cases.get_batch_status import GetBatchStatusUseCase
from app.application.use_cases.submit_bulk_create_hospitals import (
    SubmitBulkCreateHospitalsUseCase,
)
from app.domain.models import BulkCreateBatchJob
from app.infrastructure.clients.hospital_directory_api import (
    HospitalDirectoryApiGateway,
)
from app.infrastructure.repositories.in_memory_batch_repository import (
    InMemoryBatchRepository,
)
from app.infrastructure.settings import Settings
from app.infrastructure.task_dispatchers.in_memory import (
    InMemoryBackgroundBatchTaskDispatcher,
)


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    batch_repository: BatchRepository
    batch_task_dispatcher: BatchTaskDispatcher
    hospital_directory_gateway: HospitalDirectoryGateway
    submit_bulk_create_hospitals_use_case: SubmitBulkCreateHospitalsUseCase
    bulk_create_hospitals_use_case: BulkCreateHospitalsUseCase
    get_batch_status_use_case: GetBatchStatusUseCase
    http_client: httpx.AsyncClient | None = None


async def build_container(settings: Settings | None = None) -> AppContainer:
    app_settings = settings or Settings.from_env()
    http_client = httpx.AsyncClient(
        base_url=app_settings.external_api_base_url,
        timeout=app_settings.http_timeout_seconds,
    )
    batch_repository = InMemoryBatchRepository()
    hospital_directory_gateway = HospitalDirectoryApiGateway(http_client)
    csv_parser = CsvHospitalParser(max_hospitals=app_settings.max_csv_hospitals)
    retry_executor = AsyncRetryExecutor(
        RetryPolicy(
            max_attempts=app_settings.retry_max_attempts,
            initial_delay_seconds=app_settings.retry_initial_delay_seconds,
            backoff_multiplier=app_settings.retry_backoff_multiplier,
            max_delay_seconds=app_settings.retry_max_delay_seconds,
        )
    )
    bulk_create_hospitals_use_case = BulkCreateHospitalsUseCase(
        batch_repository=batch_repository,
        hospital_directory_gateway=hospital_directory_gateway,
        retry_executor=retry_executor,
        max_concurrent_requests=app_settings.concurrent_requests,
    )

    async def process_job(job: BulkCreateBatchJob) -> None:
        _ = await bulk_create_hospitals_use_case.execute(job)

    batch_task_dispatcher = _build_batch_task_dispatcher(
        backend=app_settings.batch_task_backend,
        handler=process_job,
    )

    return AppContainer(
        settings=app_settings,
        batch_repository=batch_repository,
        batch_task_dispatcher=batch_task_dispatcher,
        hospital_directory_gateway=hospital_directory_gateway,
        submit_bulk_create_hospitals_use_case=SubmitBulkCreateHospitalsUseCase(
            batch_repository=batch_repository,
            batch_task_dispatcher=batch_task_dispatcher,
            csv_parser=csv_parser,
        ),
        bulk_create_hospitals_use_case=bulk_create_hospitals_use_case,
        get_batch_status_use_case=GetBatchStatusUseCase(
            batch_repository=batch_repository
        ),
        http_client=http_client,
    )


def _build_batch_task_dispatcher(
    backend: str,
    handler: Callable[[BulkCreateBatchJob], Awaitable[None]],
) -> BatchTaskDispatcher:
    normalized_backend = backend.strip().lower()
    if normalized_backend == "in_memory":
        return InMemoryBackgroundBatchTaskDispatcher(handler)

    raise ValueError(
        "Unsupported batch task backend "
        + f"'{backend}'. Implement the BatchTaskDispatcher port for "
        + "Celery, SQS, or another worker backend."
    )


async def shutdown_container(container: AppContainer) -> None:
    await container.batch_task_dispatcher.shutdown()
    if container.http_client is not None:
        await container.http_client.aclose()
