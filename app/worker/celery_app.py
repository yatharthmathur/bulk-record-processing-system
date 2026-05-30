# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUntypedFunctionDecorator=false
from __future__ import annotations

import asyncio
from collections.abc import Mapping

from celery import Celery

from app.application.services.retry import AsyncRetryExecutor, RetryPolicy
from app.application.use_cases.bulk_create_hospitals import BulkCreateHospitalsUseCase
from app.infrastructure.bootstrap_support import (
    build_batch_repository,
    build_http_client,
)
from app.infrastructure.clients.hospital_directory_api import (
    HospitalDirectoryApiGateway,
)
from app.infrastructure.serialization.batches import (
    JSONValue,
    bulk_create_batch_job_from_dict,
)
from app.infrastructure.settings import Settings

TASK_NAME = "app.worker.process_bulk_batch"
settings = Settings.from_env()
celery_app = Celery(
    "bulk_record_processing_system",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend_url,
)
celery_app.conf.update(task_default_queue=settings.celery_queue_name)


@celery_app.task(name=TASK_NAME)
def process_bulk_batch(job_payload: Mapping[str, JSONValue]) -> None:
    asyncio.run(_process_bulk_batch(job_payload))


async def _process_bulk_batch(job_payload: Mapping[str, JSONValue]) -> None:
    runtime_settings = Settings.from_env()
    http_client = build_http_client(runtime_settings)
    batch_repository = build_batch_repository(runtime_settings)
    hospital_directory_gateway = HospitalDirectoryApiGateway(http_client)
    retry_executor = AsyncRetryExecutor(
        RetryPolicy(
            max_attempts=runtime_settings.retry_max_attempts,
            initial_delay_seconds=runtime_settings.retry_initial_delay_seconds,
            backoff_multiplier=runtime_settings.retry_backoff_multiplier,
            max_delay_seconds=runtime_settings.retry_max_delay_seconds,
        )
    )
    use_case = BulkCreateHospitalsUseCase(
        batch_repository=batch_repository,
        hospital_directory_gateway=hospital_directory_gateway,
        retry_executor=retry_executor,
        max_concurrent_requests=runtime_settings.concurrent_requests,
    )
    try:
        _ = await use_case.execute(bulk_create_batch_job_from_dict(job_payload))
    finally:
        await batch_repository.shutdown()
        await http_client.aclose()
