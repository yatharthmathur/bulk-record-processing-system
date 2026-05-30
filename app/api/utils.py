from app.api.schemas import BatchResponse, HospitalResultResponse
from app.domain.models import BatchSnapshot


def to_batch_response(snapshot: BatchSnapshot) -> BatchResponse:
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
