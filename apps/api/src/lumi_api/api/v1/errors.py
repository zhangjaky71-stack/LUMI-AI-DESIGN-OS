from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from lumi_api.domain.ids import new_uuid7
from lumi_api.idempotency.gateway import (
    AmbiguousSideEffect,
    IdempotencyConflict,
    IdempotencyFinalFailure,
    OperationInProgress,
)

from .common import ProblemDetail

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class ApiProblem(Exception):
    def __init__(
        self,
        *,
        status: int,
        code: str,
        title: str,
        detail: str,
        type_uri: str = "about:blank",
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail
        self.type_uri = type_uri
        self.errors = errors


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Any]],
    ) -> Any:
        supplied = request.headers.get("X-Request-ID")
        request_id = (
            supplied
            if supplied is not None and _REQUEST_ID_RE.fullmatch(supplied)
            else str(new_uuid7())
        )
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", str(new_uuid7()))


def _problem_response(request: Request, problem: ProblemDetail) -> JSONResponse:
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(mode="json", exclude_none=True),
        media_type="application/problem+json",
        headers={"X-Request-ID": _request_id(request)},
    )


def _simple_problem(
    request: Request,
    *,
    status: int,
    code: str,
    title: str,
    detail: str,
) -> JSONResponse:
    return _problem_response(
        request,
        ProblemDetail(
            title=title,
            status=status,
            detail=detail,
            code=code,
            request_id=_request_id(request),
            instance=str(request.url.path),
        ),
    )


def install_error_contract(app: FastAPI) -> None:
    app.add_middleware(RequestIdMiddleware)

    @app.exception_handler(ApiProblem)
    async def api_problem_handler(request: Request, exc: ApiProblem) -> JSONResponse:
        return _problem_response(
            request,
            ProblemDetail(
                type=exc.type_uri,
                title=exc.title,
                status=exc.status,
                detail=exc.detail,
                code=exc.code,
                request_id=_request_id(request),
                instance=str(request.url.path),
                errors=exc.errors,
            ),
        )

    @app.exception_handler(IdempotencyConflict)
    async def idempotency_conflict_handler(
        request: Request, exc: IdempotencyConflict
    ) -> JSONResponse:
        return _simple_problem(
            request,
            status=409,
            code=IdempotencyConflict.code,
            title="Idempotency key conflict",
            detail=str(exc),
        )

    @app.exception_handler(OperationInProgress)
    async def idempotency_in_progress_handler(
        request: Request, exc: OperationInProgress
    ) -> JSONResponse:
        return _simple_problem(
            request,
            status=409,
            code=OperationInProgress.code,
            title="Idempotent operation is still in progress",
            detail=str(exc),
        )

    @app.exception_handler(IdempotencyFinalFailure)
    async def idempotency_final_failure_handler(
        request: Request, exc: IdempotencyFinalFailure
    ) -> JSONResponse:
        return _simple_problem(
            request,
            status=409,
            code=IdempotencyFinalFailure.code,
            title="Idempotent operation cannot be replayed",
            detail=str(exc),
        )

    @app.exception_handler(AmbiguousSideEffect)
    async def ambiguous_side_effect_handler(
        request: Request, exc: AmbiguousSideEffect
    ) -> JSONResponse:
        return _simple_problem(
            request,
            status=503,
            code=AmbiguousSideEffect.code,
            title="Side effect state is ambiguous",
            detail=str(exc),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _problem_response(
            request,
            ProblemDetail(
                title="Request validation failed",
                status=422,
                detail="One or more request fields are invalid.",
                code="validation_error",
                request_id=_request_id(request),
                instance=str(request.url.path),
                errors=exc.errors(),
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return _problem_response(
            request,
            ProblemDetail(
                title="HTTP request failed",
                status=exc.status_code,
                detail=str(exc.detail),
                code="http_error",
                request_id=_request_id(request),
                instance=str(request.url.path),
            ),
        )
