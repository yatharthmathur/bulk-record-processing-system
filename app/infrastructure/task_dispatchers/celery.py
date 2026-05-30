from __future__ import annotations

from typing import Protocol

from typing_extensions import override

from app.application.ports.batch_task_dispatcher import BatchTaskDispatcher
from app.domain.models import BulkCreateBatchJob
from app.infrastructure.serialization.batches import bulk_create_batch_job_to_dict


class CeleryTaskSender(Protocol):
    def send_task(
        self,
        name: str,
        args: object | None = None,
        kwargs: dict[str, object] | None = None,
        **options: object,
    ) -> object: ...


class CeleryBatchTaskDispatcher(BatchTaskDispatcher):
    def __init__(
        self,
        celery_app: CeleryTaskSender,
        task_name: str,
        queue_name: str,
    ) -> None:
        self._celery_app: CeleryTaskSender = celery_app
        self._task_name: str = task_name
        self._queue_name: str = queue_name

    @override
    async def dispatch(self, job: BulkCreateBatchJob) -> None:
        _ = self._celery_app.send_task(
            self._task_name,
            kwargs={"job_payload": bulk_create_batch_job_to_dict(job)},
            queue=self._queue_name,
        )

    @override
    async def shutdown(self) -> None:
        return None
