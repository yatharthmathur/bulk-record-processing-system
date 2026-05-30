# pyright: reportUnknownMemberType=false
from __future__ import annotations

import json
from typing import cast
from uuid import UUID

from redis.asyncio import Redis
from typing_extensions import override

from app.application.ports.repositories import BatchRepository
from app.domain.models import BatchSnapshot
from app.infrastructure.serializers.types import JSONObject
from app.infrastructure.serializers.utils import (
    batch_snapshot_from_dict,
    batch_snapshot_to_dict,
)


class RedisBatchRepository(BatchRepository):
    def __init__(self, redis_client: Redis, key_prefix: str = "batch") -> None:
        self._redis_client: Redis = redis_client
        self._key_prefix: str = key_prefix

    @override
    async def save(self, snapshot: BatchSnapshot) -> None:
        payload = json.dumps(batch_snapshot_to_dict(snapshot))
        await self._redis_client.set(self._build_key(snapshot.batch_id), payload)

    @override
    async def get(self, batch_id: UUID) -> BatchSnapshot | None:
        raw_value = cast(
            str | bytes | None,
            await self._redis_client.get(self._build_key(batch_id)),
        )
        if raw_value is None:
            return None

        if isinstance(raw_value, bytes):
            serialized_snapshot = raw_value.decode("utf-8")
        else:
            serialized_snapshot = raw_value

        data = cast(object, json.loads(serialized_snapshot))
        if not isinstance(data, dict):
            raise TypeError(
                "Expected Redis batch payload to deserialize into an object."
            )
        return batch_snapshot_from_dict(cast(JSONObject, data))

    @override
    async def shutdown(self) -> None:
        await self._redis_client.aclose()

    def _build_key(self, batch_id: UUID) -> str:
        return f"{self._key_prefix}:{batch_id}"
