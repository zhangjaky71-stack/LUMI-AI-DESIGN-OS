from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import cast

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware

from lumi_domain import new_uuid7

from .v1.cost_router import cost_router
from .v1.errors import ApiProblem, api_problem_handler, validation_problem_handler
from .v1.router import router
from .v1.services import ApiV1Gateway


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        supplied = request.headers.get("X-Request-Id", "").strip()
        request_id = supplied if 1 <= len(supplied) <= 128 else str(new_uuid7())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response


def install_api_v1(app: FastAPI, *, gateway: ApiV1Gateway | None = None) -> None:
    if getattr(app.state, "api_v1_installed", False):
        if gateway is not None:
            app.state.api_v1_gateway = gateway
        return

    app.state.api_v1_installed = True
    if gateway is not None:
        app.state.api_v1_gateway = gateway

    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(ApiProblem, cast(Callable[..., Response], api_problem_handler))
    app.add_exception_handler(
        RequestValidationError,
        cast(Callable[..., Response], validation_problem_handler),
    )
    app.include_router(router)
    app.include_router(cost_router)


def create_contract_app(*, gateway: ApiV1Gateway | None = None) -> FastAPI:
    app = FastAPI(
        title="LUMI AI Design OS API",
        summary="Versioned product API contract for LUMI AI Design OS.",
        version="1.0.0",
        openapi_version="3.1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )
    install_api_v1(app, gateway=gateway)
    return app
