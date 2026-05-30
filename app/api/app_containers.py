from __future__ import annotations

from typing import Protocol, cast

from fastapi import Request

from app.bootstrap import AppContainer


class _ContainerState(Protocol):
    container: AppContainer


class _AppWithContainerState(Protocol):
    state: _ContainerState


def get_container(request: Request) -> AppContainer:
    app = cast(_AppWithContainerState, request.app)
    return app.state.container
