from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.domain.models import ExternalHospital, HospitalRow


class HospitalDirectoryGateway(Protocol):
    async def create_hospital(
        self, hospital: HospitalRow, batch_id: UUID
    ) -> ExternalHospital: ...

    async def activate_batch(self, batch_id: UUID) -> None: ...
