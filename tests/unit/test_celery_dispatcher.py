from __future__ import annotations

from uuid import uuid4

import pytest
from typing_extensions import override

from app.domain.models import BulkCreateBatchJob, HospitalRow
from app.infrastructure.task_dispatchers.celery import (
    CeleryBatchTaskDispatcher,
    CeleryTaskSender,
)


class FakeCeleryApp(CeleryTaskSender):
    def __init__(self) -> None:
        self.sent_tasks: list[dict[str, object]] = []

    @override
    def send_task(
        self,
        name: str,
        args: object | None = None,
        kwargs: dict[str, object] | None = None,
        **options: object,
    ) -> object:
        self.sent_tasks.append(
            {
                "task_name": name,
                "args": args,
                "kwargs": kwargs,
                "queue": options.get("queue"),
            }
        )
        return object()


@pytest.mark.asyncio
async def test_celery_dispatcher_serializes_and_dispatches_job() -> None:
    fake_celery_app = FakeCeleryApp()
    dispatcher = CeleryBatchTaskDispatcher(
        celery_app=fake_celery_app,
        task_name="app.worker.process_bulk_batch",
        queue_name="bulk_hospital_jobs",
    )
    job = BulkCreateBatchJob(
        batch_id=uuid4(),
        hospitals=(HospitalRow(row=1, name="General Hospital", address="123 Main St"),),
    )

    await dispatcher.dispatch(job)

    assert len(fake_celery_app.sent_tasks) == 1
    sent_task = fake_celery_app.sent_tasks[0]
    assert sent_task["task_name"] == "app.worker.process_bulk_batch"
    assert sent_task["queue"] == "bulk_hospital_jobs"
    assert sent_task["kwargs"] == {
        "job_payload": {
            "batch_id": str(job.batch_id),
            "hospitals": [
                {
                    "row": 1,
                    "name": "General Hospital",
                    "address": "123 Main St",
                    "phone": None,
                }
            ],
        }
    }
