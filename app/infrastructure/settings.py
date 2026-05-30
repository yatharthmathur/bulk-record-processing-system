from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = "Bulk Hospital Processing Service"
    external_api_base_url: str = "https://hospital-directory.onrender.com"
    max_csv_hospitals: int = 20
    concurrent_requests: int = 5
    http_timeout_seconds: float = 15.0
    batch_task_backend: str = "in_memory"
    retry_max_attempts: int = 3
    retry_initial_delay_seconds: float = 0.25
    retry_backoff_multiplier: float = 2.0
    retry_max_delay_seconds: float = 2.0

    @classmethod
    def from_env(cls) -> Settings:
        defaults = cls()
        return cls(
            app_name=os.getenv("APP_NAME", defaults.app_name),
            external_api_base_url=os.getenv(
                "EXTERNAL_API_BASE_URL", defaults.external_api_base_url
            ),
            max_csv_hospitals=int(
                os.getenv("MAX_CSV_HOSPITALS", str(defaults.max_csv_hospitals))
            ),
            concurrent_requests=int(
                os.getenv("CONCURRENT_REQUESTS", str(defaults.concurrent_requests))
            ),
            http_timeout_seconds=float(
                os.getenv("HTTP_TIMEOUT_SECONDS", str(defaults.http_timeout_seconds))
            ),
            batch_task_backend=os.getenv(
                "BATCH_TASK_BACKEND", defaults.batch_task_backend
            ),
            retry_max_attempts=int(
                os.getenv("RETRY_MAX_ATTEMPTS", str(defaults.retry_max_attempts))
            ),
            retry_initial_delay_seconds=float(
                os.getenv(
                    "RETRY_INITIAL_DELAY_SECONDS",
                    str(defaults.retry_initial_delay_seconds),
                )
            ),
            retry_backoff_multiplier=float(
                os.getenv(
                    "RETRY_BACKOFF_MULTIPLIER",
                    str(defaults.retry_backoff_multiplier),
                )
            ),
            retry_max_delay_seconds=float(
                os.getenv(
                    "RETRY_MAX_DELAY_SECONDS",
                    str(defaults.retry_max_delay_seconds),
                )
            ),
        )
