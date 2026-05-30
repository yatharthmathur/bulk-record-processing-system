# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from app.domain.models import BatchSnapshot, BatchStatus
from app.infrastructure.repositories.redis import RedisBatchRepository


@pytest.fixture
async def redis_repository() -> AsyncIterator[RedisBatchRepository]:
    redis_client = Redis.from_url("redis://localhost:6379/15")
    try:
        await redis_client.ping()
    except Exception:
        await redis_client.aclose()
        pytest.skip("Redis is not available")

    key_prefix = f"test-md5-{uuid4()}"
    repository = RedisBatchRepository(redis_client, key_prefix=key_prefix)
    yield repository
    keys = [key async for key in redis_client.scan_iter(match=f"{key_prefix}*")]
    if keys:
        await redis_client.delete(*keys)
    await repository.shutdown()


@pytest.mark.asyncio
async def test_redis_repository_claim_and_release_semantics(
    redis_repository: RedisBatchRepository,
) -> None:
    file_md5 = "deadbeef"
    first_batch_id = uuid4()
    second_batch_id = uuid4()

    assert (
        await redis_repository.claim_in_flight_file_md5(file_md5, first_batch_id)
        is None
    )
    assert (
        await redis_repository.claim_in_flight_file_md5(file_md5, second_batch_id)
        == first_batch_id
    )

    await redis_repository.save(
        BatchSnapshot(
            batch_id=first_batch_id,
            total_hospitals=1,
            processed_hospitals=1,
            failed_hospitals=0,
            batch_activated=True,
            status=BatchStatus.COMPLETED,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            file_md5=file_md5,
        )
    )
    await redis_repository.release_file_md5(file_md5, first_batch_id)

    assert (
        await redis_repository.claim_in_flight_file_md5(file_md5, second_batch_id)
        is None
    )
