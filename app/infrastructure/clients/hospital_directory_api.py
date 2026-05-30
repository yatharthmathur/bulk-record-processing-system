from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

import httpx
from typing_extensions import override

from app.application.ports.hospital_directory_gateway import HospitalDirectoryGateway
from app.domain.exceptions import ExternalServiceError
from app.domain.models import ExternalHospital, HospitalRow


class HospitalDirectoryApiGateway(HospitalDirectoryGateway):
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client: httpx.AsyncClient = client

    @override
    async def create_hospital(
        self, hospital: HospitalRow, batch_id: UUID
    ) -> ExternalHospital:
        payload = {
            "name": hospital.name,
            "address": hospital.address,
            "phone": hospital.phone,
            "creation_batch_id": str(batch_id),
        }

        try:
            response = await self._client.post("/hospitals/", json=payload)
            _ = response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                "Row "
                + f"{hospital.row}: failed to create hospital via upstream API. "
                + f"{self._format_http_error(exc)}"
            ) from exc

        data = cast(dict[str, object], response.json())
        raw_phone = data.get("phone")
        return ExternalHospital(
            id=self._required_int(data["id"]),
            name=str(data["name"]),
            address=str(data["address"]),
            phone=None if raw_phone is None else str(raw_phone),
            creation_batch_id=self._parse_uuid(
                self._optional_str(data.get("creation_batch_id"))
            ),
            active=bool(data.get("active", False)),
            created_at=self._parse_datetime(self._optional_str(data.get("created_at"))),
        )

    @override
    async def activate_batch(self, batch_id: UUID) -> None:
        try:
            response = await self._client.patch(f"/hospitals/batch/{batch_id}/activate")
            _ = response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ExternalServiceError(
                f"Failed to activate batch '{batch_id}'. {self._format_http_error(exc)}"
            ) from exc

    @staticmethod
    def _required_int(raw_value: object) -> int:
        if isinstance(raw_value, bool):
            return int(raw_value)
        if isinstance(raw_value, int):
            return raw_value
        if isinstance(raw_value, str):
            return int(raw_value)
        raise ExternalServiceError(
            f"Expected an integer-compatible value, got {type(raw_value).__name__}."
        )

    @staticmethod
    def _optional_str(raw_value: object) -> str | None:
        if raw_value is None:
            return None
        return str(raw_value)

    @staticmethod
    def _parse_uuid(raw_value: str | None) -> UUID | None:
        if raw_value is None:
            return None
        return UUID(raw_value)

    @staticmethod
    def _parse_datetime(raw_value: str | None) -> datetime | None:
        if raw_value is None:
            return None

        normalized = raw_value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)

    @staticmethod
    def _format_http_error(exc: httpx.HTTPError) -> str:
        if isinstance(exc, httpx.HTTPStatusError):
            response = exc.response
            try:
                body = cast(object, response.json())
            except ValueError:
                body = response.text
            return f"status={response.status_code}, body={body}"

        return str(exc)
