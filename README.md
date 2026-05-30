# Bulk Hospital Processing Service

A FastAPI service for bulk hospital creation against the external Hospital Directory API:
`https://hospital-directory.onrender.com`

## Features

- `POST /hospitals/bulk` accepts a CSV upload and queues bulk processing in the background
- Concurrent upstream hospital creation for faster throughput
- Automatic retries with exponential backoff for hospital creation and batch activation
- Configurable task-dispatch port so the background runner can be replaced with Celery, SQS + workers, or another queue backend
- In-memory batch tracking with `GET /batches/{batch_id}`
- CSV validation endpoint: `POST /hospitals/bulk/validate`
- Ports and adapters architecture with clear separation between domain, application, API, and infrastructure
- Docker, `uv`, and pre-commit support
- Unit and integration tests

## Architecture

```text
app/
  api/                FastAPI routes, schemas, dependency access
  application/
    ports/            Protocol-based interfaces for repositories, gateways, and task dispatch
    services/         Reusable application services (CSV parsing, retry policy)
    use_cases/        Submit batch, process batch, validate CSV, get status
  domain/             Core models and domain exceptions
  infrastructure/     External API adapter, settings, repository, task dispatcher
```

### Background processing flow

1. Validate and parse uploaded CSV
2. Generate a `batch_id`
3. Persist a batch snapshot with status `queued`
4. Dispatch a background job through the `BatchTaskDispatcher` port
5. Worker/dispatcher processes hospitals concurrently against `POST /hospitals/`
6. Each hospital create attempt is retried up to 3 times with exponential backoff
7. If all rows succeed, activation is retried against
   `PATCH /hospitals/batch/{batch_id}/activate`
8. Final results are stored and can be polled with `GET /batches/{batch_id}`

## Extensibility

The app now separates **submission** from **execution**:

- `SubmitBulkCreateHospitalsUseCase` validates input and enqueues work
- `BulkCreateHospitalsUseCase` performs the actual processing
- `BatchTaskDispatcher` is the port for the execution backend

The built-in adapter is `InMemoryBackgroundBatchTaskDispatcher`, which runs jobs in-process using `asyncio.create_task(...)`.

To move to Celery, SQS + workers, Redis Queue, or another execution system, implement the `BatchTaskDispatcher` port and wire it in `app/bootstrap.py`.

## CSV format

Accepted headers:
- `name,address`
- `name,address,phone`

Rules:
- `name` is required
- `address` is required
- `phone` is optional
- maximum 20 hospital rows per file
- UTF-8 CSV only

## API endpoints

### `GET /health`
Health check.

### `POST /hospitals/bulk`
Multipart form upload with a `file` field.

This endpoint now returns `202 Accepted` after the batch is queued.

Example response:

```json
{
  "batch_id": "550e8400-e29b-41d4-a716-446655440000",
  "total_hospitals": 2,
  "processed_hospitals": 0,
  "failed_hospitals": 0,
  "processing_time_seconds": null,
  "batch_activated": false,
  "progress_percentage": 0.0,
  "status": "queued",
  "started_at": "2026-05-30T12:00:00Z",
  "completed_at": null,
  "hospitals": []
}
```

### `GET /batches/{batch_id}`
Returns the latest stored status for a processed batch.
Each hospital result includes `attempts` so retry behavior is visible.

### `POST /hospitals/bulk/validate`
Validates CSV shape without calling the external API.

## Local development

### 1. Install dependencies

```bash
uv sync --dev
```

### 2. Install git hooks

```bash
uv run pre-commit install
uv run pre-commit install --hook-type pre-push
```

### 3. Run the API

```bash
uv run uvicorn app.main:app --reload
```

Open Swagger UI at `http://localhost:8000/docs`.

## Quality tooling

Pre-commit hooks include:
- `pre-commit-hooks` sanity checks
- `uv-lock` to keep `uv.lock` in sync with `pyproject.toml`
- `ruff-check --fix`
- `ruff-format`
- `basedpyright`
- `pytest` on `pre-push`

Run them manually with:

```bash
uv run pre-commit run --all-files
uv run pre-commit run --all-files --hook-stage pre-push
```

## Docker

### Build and run with Docker Compose

```bash
docker compose up --build
```

## Configuration

The project uses `uv` with `pyproject.toml` and `uv.lock` to keep local and container environments aligned.

Environment variables:

- `APP_NAME`
- `EXTERNAL_API_BASE_URL`
- `MAX_CSV_HOSPITALS`
- `CONCURRENT_REQUESTS`
- `HTTP_TIMEOUT_SECONDS`
- `BATCH_TASK_BACKEND`
- `RETRY_MAX_ATTEMPTS`
- `RETRY_INITIAL_DELAY_SECONDS`
- `RETRY_BACKOFF_MULTIPLIER`
- `RETRY_MAX_DELAY_SECONDS`

Built-in task backend values:
- `in_memory`

## Testing

```bash
uv run basedpyright .
uv run pytest
```

## Notes

- Batch storage is still in memory, so batch history is lost when the service restarts.
- The default dispatcher is in-process background execution. For production-scale reliability, a durable queue adapter such as Celery or SQS workers is recommended.
- Because the upstream API does not expose rollback semantics, partial failures can leave some hospitals created upstream but not activated.
