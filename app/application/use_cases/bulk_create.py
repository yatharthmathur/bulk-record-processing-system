from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from app.application.ports.external_apis import HospitalDirectoryGateway
from app.application.ports.repositories import BatchRepository
from app.application.services.retry import AsyncRetryExecutor
from app.domain.exceptions import BatchNotFoundError, ExternalServiceError
from app.domain.models import (
    BatchSnapshot,
    BatchStatus,
    BulkCreateBatchJob,
    HospitalProcessingResult,
    HospitalRow,
)


class BulkCreateUseCase:
    def __init__(
        self,
        batch_repository: BatchRepository,
        hospital_directory_gateway: HospitalDirectoryGateway,
        retry_executor: AsyncRetryExecutor,
        max_concurrent_requests: int,
    ) -> None:
        self._batch_repository: BatchRepository = batch_repository
        self._hospital_directory_gateway: HospitalDirectoryGateway = (
            hospital_directory_gateway
        )
        self._retry_executor: AsyncRetryExecutor = retry_executor
        self._max_concurrent_requests: int = max_concurrent_requests

    async def execute(self, job: BulkCreateBatchJob) -> BatchSnapshot:
        existing_snapshot = await self._batch_repository.get(job.batch_id)
        if existing_snapshot is None:
            raise BatchNotFoundError(str(job.batch_id))

        snapshot = replace(existing_snapshot, status=BatchStatus.PROCESSING)
        await self._batch_repository.save(snapshot)

        results = await self._create_hospitals(
            batch_id=job.batch_id,
            hospitals=list(job.hospitals),
            snapshot=snapshot,
        )

        successful = sum(1 for result in results if result.hospital_id is not None)
        failed = len(results) - successful
        batch_activated = False
        status = BatchStatus.PARTIAL_FAILURE if failed else BatchStatus.COMPLETED

        if failed == 0:
            activation_outcome = await self._retry_executor.run(
                lambda: self._hospital_directory_gateway.activate_batch(job.batch_id)
            )
            if activation_outcome.succeeded:
                batch_activated = True
                results = [
                    replace(
                        result,
                        status="created_and_activated",
                        attempts=max(result.attempts, activation_outcome.attempts),
                    )
                    for result in results
                ]
            else:
                status = BatchStatus.ACTIVATION_FAILED
                results = [
                    replace(
                        result,
                        status="created_activation_failed",
                        attempts=max(result.attempts, activation_outcome.attempts),
                        error=str(activation_outcome.error),
                    )
                    for result in results
                ]

        completed_at = datetime.now(UTC)
        processing_time_seconds = round(
            (completed_at - existing_snapshot.started_at).total_seconds(),
            3,
        )
        final_snapshot = BatchSnapshot(
            batch_id=job.batch_id,
            total_hospitals=len(job.hospitals),
            processed_hospitals=successful,
            failed_hospitals=failed,
            batch_activated=batch_activated,
            status=status,
            hospitals=tuple(sorted(results, key=lambda item: item.row)),
            started_at=existing_snapshot.started_at,
            completed_at=completed_at,
            processing_time_seconds=processing_time_seconds,
            file_md5=existing_snapshot.file_md5,
        )
        await self._batch_repository.save(final_snapshot)
        if final_snapshot.file_md5 is not None:
            await self._batch_repository.release_file_md5(
                final_snapshot.file_md5, final_snapshot.batch_id
            )
        return final_snapshot

    async def _create_hospitals(
        self,
        batch_id: UUID,
        hospitals: list[HospitalRow],
        snapshot: BatchSnapshot,
    ) -> list[HospitalProcessingResult]:
        semaphore = asyncio.Semaphore(self._max_concurrent_requests)
        tasks = [
            asyncio.create_task(
                self._create_single_hospital(
                    batch_id=batch_id,
                    hospital=hospital,
                    semaphore=semaphore,
                )
            )
            for hospital in hospitals
        ]

        successful = 0
        failed = 0
        results: list[HospitalProcessingResult] = []

        for completed_task in asyncio.as_completed(tasks):
            result = await completed_task
            results.append(result)
            if result.hospital_id is None:
                failed += 1
            else:
                successful += 1

            progress_snapshot = replace(
                snapshot,
                processed_hospitals=successful,
                failed_hospitals=failed,
                hospitals=tuple(sorted(results, key=lambda item: item.row)),
            )
            await self._batch_repository.save(progress_snapshot)

        return results

    async def _create_single_hospital(
        self,
        batch_id: UUID,
        hospital: HospitalRow,
        semaphore: asyncio.Semaphore,
    ) -> HospitalProcessingResult:
        async with semaphore:
            outcome = await self._retry_executor.run(
                lambda: self._hospital_directory_gateway.create_hospital(
                    hospital, batch_id
                )
            )
            if outcome.succeeded and outcome.value is not None:
                created = outcome.value
                return HospitalProcessingResult(
                    row=hospital.row,
                    hospital_id=created.id,
                    name=created.name,
                    status="created",
                    attempts=outcome.attempts,
                )

            error = outcome.error or ExternalServiceError(
                f"Row {hospital.row}: hospital creation failed."
            )
            return HospitalProcessingResult(
                row=hospital.row,
                hospital_id=None,
                name=hospital.name,
                status="failed",
                attempts=outcome.attempts,
                error=str(error),
            )
