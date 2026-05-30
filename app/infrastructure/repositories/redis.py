# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
from __future__ import annotations

import json
from typing import cast
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import WatchError
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
    async def claim_in_flight_file_md5(
        self, file_md5: str, batch_id: UUID
    ) -> UUID | None:
        md5_key = self._build_md5_key(file_md5)
        while True:
            existing_batch_id = await self._resolve_in_flight_batch_id(file_md5)
            if existing_batch_id is not None:
                return existing_batch_id

            try:
                async with self._redis_client.pipeline(transaction=True) as pipe:
                    _ = await pipe.watch(md5_key)
                    mapped_batch_id = cast(
                        str | bytes | None,
                        await pipe.get(md5_key),
                    )
                    if mapped_batch_id is not None:
                        mapped_id = self._decode_batch_id(mapped_batch_id)
                        if mapped_id != batch_id:
                            existing_snapshot = await self.get(mapped_id)
                            if (
                                existing_snapshot is None
                                or not existing_snapshot.is_finished
                            ):
                                return mapped_id

                    _ = pipe.multi()
                    _ = pipe.set(md5_key, str(batch_id))
                    _ = await pipe.execute()
                    return None
            except WatchError:
                continue

    @override
    async def release_file_md5(self, file_md5: str, batch_id: UUID) -> None:
        md5_key = self._build_md5_key(file_md5)
        while True:
            try:
                async with self._redis_client.pipeline(transaction=True) as pipe:
                    _ = await pipe.watch(md5_key)
                    mapped_batch_id = cast(
                        str | bytes | None,
                        await pipe.get(md5_key),
                    )
                    if mapped_batch_id is None:
                        return
                    if self._decode_batch_id(mapped_batch_id) != batch_id:
                        return

                    _ = pipe.multi()
                    _ = pipe.delete(md5_key)
                    _ = await pipe.execute()
                    return
            except WatchError:
                continue

    @override
    async def shutdown(self) -> None:
        await self._redis_client.aclose()

    async def _resolve_in_flight_batch_id(self, file_md5: str) -> UUID | None:
        mapped_batch_id = cast(
            str | bytes | None,
            await self._redis_client.get(self._build_md5_key(file_md5)),
        )
        if mapped_batch_id is None:
            return None

        batch_id = self._decode_batch_id(mapped_batch_id)
        existing_snapshot = await self.get(batch_id)
        if existing_snapshot is None or not existing_snapshot.is_finished:
            return batch_id
        return None

    def _build_key(self, batch_id: UUID) -> str:
        return f"{self._key_prefix}:{batch_id}"

    def _build_md5_key(self, file_md5: str) -> str:
        return f"{self._key_prefix}:md5:{file_md5}"

    @staticmethod
    def _decode_batch_id(value: str | bytes) -> UUID:
        if isinstance(value, bytes):
            return UUID(value.decode("utf-8"))
        return UUID(value)
