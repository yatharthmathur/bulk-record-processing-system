from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.domain.models import (
    BatchSnapshot,
    BatchStatus,
    BulkCreateBatchJob,
    HospitalProcessingResult,
    HospitalRow,
)
from app.infrastructure.serializers.utils import (
    batch_snapshot_from_dict,
    batch_snapshot_to_dict,
    bulk_create_batch_job_from_dict,
    bulk_create_batch_job_to_dict,
)


def test_batch_snapshot_serialization_round_trip() -> None:
    snapshot = BatchSnapshot(
        batch_id=uuid4(),
        total_hospitals=2,
        processed_hospitals=1,
        failed_hospitals=1,
        batch_activated=False,
        status=BatchStatus.PARTIAL_FAILURE,
        hospitals=(
            HospitalProcessingResult(
                row=1,
                hospital_id=101,
                name="General Hospital",
                status="created",
                attempts=2,
            ),
            HospitalProcessingResult(
                row=2,
                hospital_id=None,
                name="City Clinic",
                status="failed",
                attempts=3,
                error="simulated failure",
            ),
        ),
        started_at=datetime(2026, 5, 30, 12, 0, 0, tzinfo=UTC),
        completed_at=datetime(2026, 5, 30, 12, 0, 5, tzinfo=UTC),
        processing_time_seconds=5.0,
    )

    serialized = batch_snapshot_to_dict(snapshot)
    round_tripped = batch_snapshot_from_dict(serialized)

    assert round_tripped == snapshot


def test_bulk_create_batch_job_serialization_round_trip() -> None:
    job = BulkCreateBatchJob(
        batch_id=uuid4(),
        hospitals=(
            HospitalRow(row=1, name="General Hospital", address="123 Main St"),
            HospitalRow(
                row=2, name="City Clinic", address="99 Elm St", phone="555-0101"
            ),
        ),
    )

    serialized = bulk_create_batch_job_to_dict(job)
    round_tripped = bulk_create_batch_job_from_dict(serialized)

    assert round_tripped == job
