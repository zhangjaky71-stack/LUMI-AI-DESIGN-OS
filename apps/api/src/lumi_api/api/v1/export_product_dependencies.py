from __future__ import annotations

from collections.abc import Generator
from contextlib import AbstractContextManager
from typing import Annotated, Protocol

from fastapi import Depends, Request
from lumi_export_engine import ExportEngine

from .errors import ApiProblem


class ExportEngineFactory(Protocol):
    def __call__(self) -> AbstractContextManager[ExportEngine]: ...


def get_export_engine(request: Request) -> Generator[ExportEngine, None, None]:
    factory = getattr(request.app.state, "export_engine_factory", None)
    if factory is None:
        raise ApiProblem(
            status=503,
            code="export_engine_not_composed",
            title="Export engine unavailable",
            detail="NODE-49 Export Engine is installed but the request-scoped production factory is not composed in this deployment.",
        )
    with factory() as engine:
        yield engine


ExportEngineDependency = Annotated[ExportEngine, Depends(get_export_engine)]
