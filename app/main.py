from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.bootstrap import AppContainer, build_container, shutdown_container
from app.domain.exceptions import BatchNotFoundError, CsvValidationError


async def handle_csv_validation_error(
    _request: Request,
    exc: CsvValidationError,
) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": exc.errors})


async def handle_batch_not_found_error(
    _request: Request,
    exc: BatchNotFoundError,
) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": [str(exc)]})


def register_exception_handlers(app: FastAPI) -> None:
    _ = app.exception_handler(CsvValidationError)(handle_csv_validation_error)
    _ = app.exception_handler(BatchNotFoundError)(handle_batch_not_found_error)


def create_app(container: AppContainer | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        active_container = container or await build_container()
        app.state.container = active_container
        try:
            yield
        finally:
            await shutdown_container(active_container)

    app = FastAPI(
        title="Bulk Hospital Processing Service",
        version="1.0.0",
        lifespan=lifespan,
    )
    register_exception_handlers(app)
    app.include_router(router)
    return app


app = create_app()
