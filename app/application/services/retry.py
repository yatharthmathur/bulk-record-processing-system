from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    initial_delay_seconds: float = 0.25
    backoff_multiplier: float = 2.0
    max_delay_seconds: float = 2.0


@dataclass(frozen=True, slots=True)
class RetryOutcome(Generic[T]):
    value: T | None
    attempts: int
    error: Exception | None = None

    @property
    def succeeded(self) -> bool:
        return self.error is None


class AsyncRetryExecutor:
    def __init__(
        self,
        retry_policy: RetryPolicy,
        sleep_func: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._retry_policy: RetryPolicy = retry_policy
        self._sleep_func: Callable[[float], Awaitable[None]] = sleep_func

    async def run(self, operation: Callable[[], Awaitable[T]]) -> RetryOutcome[T]:
        attempts = 0
        delay_seconds = self._retry_policy.initial_delay_seconds
        last_error: Exception | None = None

        while attempts < self._retry_policy.max_attempts:
            attempts += 1
            try:
                value = await operation()
                return RetryOutcome(value=value, attempts=attempts)
            except Exception as exc:
                last_error = exc
                if attempts >= self._retry_policy.max_attempts:
                    break

                await self._sleep_func(delay_seconds)
                delay_seconds = min(
                    delay_seconds * self._retry_policy.backoff_multiplier,
                    self._retry_policy.max_delay_seconds,
                )

        return RetryOutcome(value=None, attempts=attempts, error=last_error)
