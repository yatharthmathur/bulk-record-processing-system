# pyright: reportUnknownMemberType=false
from __future__ import annotations

import httpx
from redis.asyncio import Redis

from app.application.ports.repositories import BatchRepository
from app.infrastructure.repositories.in_memory import (
    InMemoryBatchRepository,
)
from app.infrastructure.repositories.redis import RedisBatchRepository
from app.infrastructure.settings import Settings


def build_http_client(settings: Settings) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.external_api_base_url,
        timeout=settings.http_timeout_seconds,
    )


def build_batch_repository(settings: Settings) -> BatchRepository:
    normalized_backend = settings.batch_repository_backend.strip().lower()
    if normalized_backend == "in_memory":
        return InMemoryBatchRepository()
    if normalized_backend == "redis":
        redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
        return RedisBatchRepository(
            redis_client, key_prefix=settings.redis_batch_key_prefix
        )

    raise ValueError(
        "Unsupported batch repository backend "
        + f"'{settings.batch_repository_backend}'. Use 'in_memory' or 'redis'."
    )
