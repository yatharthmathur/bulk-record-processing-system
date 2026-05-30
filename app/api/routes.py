from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile

from app.api.app_containers import get_container
from app.api.schemas import BatchResponse, HealthResponse
from app.api.utils import to_batch_response
from app.bootstrap import AppContainer

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
    return to_batch_response(snapshot)


@router.get("/batches/{batch_id}", response_model=BatchResponse)
async def get_status(
    batch_id: UUID,
    container: Annotated[AppContainer, Depends(get_container)],
) -> BatchResponse:
    snapshot = await container.get_batch_status_use_case.execute(batch_id)
    return to_batch_response(snapshot)
