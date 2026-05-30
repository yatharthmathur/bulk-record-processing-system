from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.domain.models import BatchSnapshot


class BatchRepository(Protocol):
    async def save(self, snapshot: BatchSnapshot) -> None: ...

    async def get(self, batch_id: UUID) -> BatchSnapshot | None: ...

    async def claim_in_flight_file_md5(
        self, file_md5: str, batch_id: UUID
    ) -> UUID | None: ...

    async def release_file_md5(self, file_md5: str, batch_id: UUID) -> None: ...

    async def shutdown(self) -> None: ...
