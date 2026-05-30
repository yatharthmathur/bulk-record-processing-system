from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import cast

import httpx

from app.application.ports.external_apis import HospitalDirectoryGateway
from app.application.ports.repositories import BatchRepository
from app.application.ports.task_dispatchers import BatchTaskDispatcher
from app.application.services.csv_parser import HospitalCsvParser
from app.application.services.retry import AsyncRetryExecutor, RetryPolicy
from app.application.use_cases.bulk_create import BulkCreateUseCase
from app.application.use_cases.get_status import GetBatchStatusUseCase
from app.application.use_cases.submit_task import (
    SubmitBulkCreateTaskUseCase,
)
from app.domain.models import BulkCreateBatchJob
from app.infrastructure.clients.external_api import (
    HospitalDirectoryApiGateway,
)
from app.infrastructure.settings import Settings
from app.infrastructure.task_dispatchers.celery import (
    CeleryBatchTaskDispatcher,
    CeleryTaskSender,
)
from app.infrastructure.task_dispatchers.in_memory import (
    InMemoryBackgroundBatchTaskDispatcher,
)
from app.infrastructure.utils import (
    build_batch_repository,
    build_http_client,
)
from app.workers.constants import TASK_NAME
from app.workers.tasks import celery_app


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    batch_repository: BatchRepository
    batch_task_dispatcher: BatchTaskDispatcher
    hospital_directory_gateway: HospitalDirectoryGateway
    submit_bulk_create_hospitals_use_case: SubmitBulkCreateTaskUseCase
    bulk_create_hospitals_use_case: BulkCreateUseCase
    get_batch_status_use_case: GetBatchStatusUseCase
    http_client: httpx.AsyncClient | None = None


async def build_container(settings: Settings | None = None) -> AppContainer:
    app_settings = settings or Settings.from_env()
    http_client = build_http_client(app_settings)
    batch_repository = build_batch_repository(app_settings)
    hospital_directory_gateway = HospitalDirectoryApiGateway(http_client)
    csv_parser = HospitalCsvParser(max_hospitals=app_settings.max_csv_hospitals)
    retry_executor = AsyncRetryExecutor(
        RetryPolicy(
            max_attempts=app_settings.retry_max_attempts,
            initial_delay_seconds=app_settings.retry_initial_delay_seconds,
            backoff_multiplier=app_settings.retry_backoff_multiplier,
            max_delay_seconds=app_settings.retry_max_delay_seconds,
        )
    )
    bulk_create_hospitals_use_case = BulkCreateUseCase(
        batch_repository=batch_repository,
        hospital_directory_gateway=hospital_directory_gateway,
        retry_executor=retry_executor,
        max_concurrent_requests=app_settings.concurrent_requests,
    )

    async def process_job(job: BulkCreateBatchJob) -> None:
        _ = await bulk_create_hospitals_use_case.execute(job)

    batch_task_dispatcher = _build_batch_task_dispatcher(
        settings=app_settings,
        handler=process_job,
    )

    return AppContainer(
        settings=app_settings,
        batch_repository=batch_repository,
        batch_task_dispatcher=batch_task_dispatcher,
        hospital_directory_gateway=hospital_directory_gateway,
        submit_bulk_create_hospitals_use_case=SubmitBulkCreateTaskUseCase(
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
    settings: Settings,
    handler: Callable[[BulkCreateBatchJob], Awaitable[None]],
) -> BatchTaskDispatcher:
    normalized_backend = settings.batch_task_backend.strip().lower()
    if normalized_backend == "in_memory":
        return InMemoryBackgroundBatchTaskDispatcher(handler)
    if normalized_backend == "celery":
        return CeleryBatchTaskDispatcher(
            celery_app=cast(CeleryTaskSender, cast(object, celery_app)),
            task_name=TASK_NAME,
            queue_name=settings.celery_queue_name,
        )

    raise ValueError(
        "Unsupported batch task backend "
        + f"'{settings.batch_task_backend}'. Use 'in_memory' or 'celery'."
    )


async def shutdown_container(container: AppContainer) -> None:
    await container.batch_task_dispatcher.shutdown()
    await container.batch_repository.shutdown()
    if container.http_client is not None:
        await container.http_client.aclose()
