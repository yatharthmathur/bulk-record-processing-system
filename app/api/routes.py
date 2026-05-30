from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile

from app.api.dependencies import get_container
from app.api.schemas import (
    BatchResponse,
    CsvValidationResponse,
    HealthResponse,
    HospitalResultResponse,
)
from app.bootstrap import AppContainer
from app.domain.models import BatchSnapshot, CsvValidationSummary

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health(
    container: Annotated[AppContainer, Depends(get_container)],
) -> HealthResponse:
    return HealthResponse(status="ok", service=container.settings.app_name)


@router.post("/hospitals/bulk", response_model=BatchResponse, status_code=202)
async def bulk_create_hospitals(
    file: Annotated[UploadFile, File(...)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> BatchResponse:
    raw_csv = await file.read()
    snapshot = await container.submit_bulk_create_hospitals_use_case.execute(raw_csv)
    return _to_batch_response(snapshot)


@router.post(
    "/hospitals/bulk/validate",
    response_model=CsvValidationResponse,
)
async def validate_bulk_csv(
    file: Annotated[UploadFile, File(...)],
    container: Annotated[AppContainer, Depends(get_container)],
) -> CsvValidationResponse:
    raw_csv = await file.read()
    summary = container.validate_csv_use_case.execute(raw_csv)
    return _to_csv_validation_response(summary)


@router.get("/batches/{batch_id}", response_model=BatchResponse)
async def get_batch_status(
    batch_id: UUID,
    container: Annotated[AppContainer, Depends(get_container)],
) -> BatchResponse:
    snapshot = await container.get_batch_status_use_case.execute(batch_id)
    return _to_batch_response(snapshot)


def _to_batch_response(snapshot: BatchSnapshot) -> BatchResponse:
    return BatchResponse(
        batch_id=snapshot.batch_id,
        total_hospitals=snapshot.total_hospitals,
        processed_hospitals=snapshot.processed_hospitals,
        failed_hospitals=snapshot.failed_hospitals,
        processing_time_seconds=snapshot.processing_time_seconds,
        batch_activated=snapshot.batch_activated,
        progress_percentage=snapshot.progress_percentage,
        status=snapshot.status.value,
        started_at=snapshot.started_at,
        completed_at=snapshot.completed_at,
        hospitals=[
            HospitalResultResponse(
                row=hospital.row,
                hospital_id=hospital.hospital_id,
                name=hospital.name,
                status=hospital.status,
                attempts=hospital.attempts,
                error=hospital.error,
            )
            for hospital in snapshot.hospitals
        ],
    )


def _to_csv_validation_response(summary: CsvValidationSummary) -> CsvValidationResponse:
    return CsvValidationResponse(
        valid=summary.valid,
        total_hospitals=summary.total_hospitals,
        max_hospitals=summary.max_hospitals,
        columns=list(summary.columns),
    )
