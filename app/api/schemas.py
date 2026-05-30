from __future__ import annotations

from datetime import datetime
from typing import ClassVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ErrorResponse(BaseModel):
    detail: list[str]


class HospitalResultResponse(BaseModel):
    row: int
    hospital_id: int | None = None
    name: str
    status: str
    attempts: int = 0
    error: str | None = None


class BatchResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(use_enum_values=True)

    batch_id: UUID
    total_hospitals: int
    processed_hospitals: int
    failed_hospitals: int
    processing_time_seconds: float | None = None
    batch_activated: bool
    progress_percentage: float
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    hospitals: list[HospitalResultResponse]


class CsvValidationResponse(BaseModel):
    valid: bool
    total_hospitals: int
    max_hospitals: int
    columns: list[str]


class HealthResponse(BaseModel):
    status: str
    service: str
