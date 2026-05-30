from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID


class BatchStatus(StrEnum):
    RECEIVED = "received"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIAL_FAILURE = "partial_failure"
    ACTIVATION_FAILED = "activation_failed"


@dataclass(frozen=True, slots=True)
class HospitalRow:
    row: int
    name: str
    address: str
    phone: str | None = None


@dataclass(frozen=True, slots=True)
class BulkCreateBatchJob:
    batch_id: UUID
    hospitals: tuple[HospitalRow, ...]


@dataclass(frozen=True, slots=True)
class ExternalHospital:
    id: int
    name: str
    address: str
    phone: str | None
    creation_batch_id: UUID | None
    active: bool
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class HospitalProcessingResult:
    row: int
    hospital_id: int | None
    name: str
    status: str
    attempts: int = 0
    error: str | None = None


@dataclass(frozen=True, slots=True)
class CsvValidationSummary:
    valid: bool
    total_hospitals: int
    max_hospitals: int
    columns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BatchSnapshot:
    batch_id: UUID
    total_hospitals: int
    processed_hospitals: int
    failed_hospitals: int
    batch_activated: bool
    status: BatchStatus
    hospitals: tuple[HospitalProcessingResult, ...] = field(default_factory=tuple)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    processing_time_seconds: float | None = None

    @property
    def attempted_hospitals(self) -> int:
        return self.processed_hospitals + self.failed_hospitals

    @property
    def progress_percentage(self) -> float:
        if self.total_hospitals == 0:
            return 100.0
        return round((self.attempted_hospitals / self.total_hospitals) * 100, 2)

    @property
    def is_finished(self) -> bool:
        return self.status in {
            BatchStatus.COMPLETED,
            BatchStatus.PARTIAL_FAILURE,
            BatchStatus.ACTIVATION_FAILED,
        }
