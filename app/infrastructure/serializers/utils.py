from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import cast
from uuid import UUID

from app.domain.models import (
    BatchSnapshot,
    BatchStatus,
    BulkCreateBatchJob,
    HospitalProcessingResult,
    HospitalRow,
)
from app.infrastructure.serializers.types import JSONObject, JSONValue


def batch_snapshot_to_dict(snapshot: BatchSnapshot) -> JSONObject:
    return {
        "batch_id": str(snapshot.batch_id),
        "total_hospitals": snapshot.total_hospitals,
        "processed_hospitals": snapshot.processed_hospitals,
        "failed_hospitals": snapshot.failed_hospitals,
        "batch_activated": snapshot.batch_activated,
        "status": snapshot.status.value,
        "hospitals": [
            hospital_processing_result_to_dict(result) for result in snapshot.hospitals
        ],
        "started_at": snapshot.started_at.isoformat(),
        "completed_at": (
            snapshot.completed_at.isoformat()
            if snapshot.completed_at is not None
            else None
        ),
        "processing_time_seconds": snapshot.processing_time_seconds,
    }


def batch_snapshot_from_dict(data: Mapping[str, JSONValue]) -> BatchSnapshot:
    hospitals_raw = _require_list(data, "hospitals")
    hospitals = tuple(
        hospital_processing_result_from_dict(_require_dict(item, "hospital result"))
        for item in hospitals_raw
    )
    return BatchSnapshot(
        batch_id=UUID(_require_str(data, "batch_id")),
        total_hospitals=_require_int(data, "total_hospitals"),
        processed_hospitals=_require_int(data, "processed_hospitals"),
        failed_hospitals=_require_int(data, "failed_hospitals"),
        batch_activated=_require_bool(data, "batch_activated"),
        status=BatchStatus(_require_str(data, "status")),
        hospitals=hospitals,
        started_at=datetime.fromisoformat(_require_str(data, "started_at")),
        completed_at=_optional_datetime(data.get("completed_at")),
        processing_time_seconds=_optional_float(data.get("processing_time_seconds")),
    )


def bulk_create_batch_job_to_dict(job: BulkCreateBatchJob) -> JSONObject:
    return {
        "batch_id": str(job.batch_id),
        "hospitals": [hospital_row_to_dict(hospital) for hospital in job.hospitals],
    }


def bulk_create_batch_job_from_dict(
    data: Mapping[str, JSONValue],
) -> BulkCreateBatchJob:
    hospitals_raw = _require_list(data, "hospitals")
    hospitals = tuple(
        hospital_row_from_dict(_require_dict(item, "hospital row"))
        for item in hospitals_raw
    )
    return BulkCreateBatchJob(
        batch_id=UUID(_require_str(data, "batch_id")),
        hospitals=hospitals,
    )


def hospital_row_to_dict(hospital: HospitalRow) -> JSONObject:
    return {
        "row": hospital.row,
        "name": hospital.name,
        "address": hospital.address,
        "phone": hospital.phone,
    }


def hospital_row_from_dict(data: Mapping[str, JSONValue]) -> HospitalRow:
    return HospitalRow(
        row=_require_int(data, "row"),
        name=_require_str(data, "name"),
        address=_require_str(data, "address"),
        phone=_optional_str(data.get("phone")),
    )


def hospital_processing_result_to_dict(result: HospitalProcessingResult) -> JSONObject:
    return {
        "row": result.row,
        "hospital_id": result.hospital_id,
        "name": result.name,
        "status": result.status,
        "attempts": result.attempts,
        "error": result.error,
    }


def hospital_processing_result_from_dict(
    data: Mapping[str, JSONValue],
) -> HospitalProcessingResult:
    return HospitalProcessingResult(
        row=_require_int(data, "row"),
        hospital_id=_optional_int(data.get("hospital_id")),
        name=_require_str(data, "name"),
        status=_require_str(data, "status"),
        attempts=_require_int(data, "attempts"),
        error=_optional_str(data.get("error")),
    )


def _require_dict(value: JSONValue, context: str) -> JSONObject:
    if not isinstance(value, dict):
        raise TypeError(f"Expected object for {context}.")
    return cast(JSONObject, value)


def _require_list(data: Mapping[str, JSONValue], key: str) -> list[JSONValue]:
    value = data.get(key)
    if not isinstance(value, list):
        raise TypeError(f"Expected list for '{key}'.")
    return value


def _require_str(data: Mapping[str, JSONValue], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise TypeError(f"Expected string for '{key}'.")
    return value


def _require_int(data: Mapping[str, JSONValue], key: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"Expected integer for '{key}'.")
    return value


def _require_bool(data: Mapping[str, JSONValue], key: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise TypeError(f"Expected boolean for '{key}'.")
    return value


def _optional_str(value: JSONValue | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("Expected optional string value.")
    return value


def _optional_int(value: JSONValue | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("Expected optional integer value.")
    return value


def _optional_float(value: JSONValue | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("Expected optional float value.")
    return float(value)


def _optional_datetime(value: JSONValue | None) -> datetime | None:
    raw_value = _optional_str(value)
    if raw_value is None:
        return None
    return datetime.fromisoformat(raw_value)
