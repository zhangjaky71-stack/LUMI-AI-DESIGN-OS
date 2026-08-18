from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from time import perf_counter
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
from lumi_api.observability import (
    DeterministicSampler,
    LogLevel,
    MetricPoint,
    SafeTelemetry,
    SamplingDecision,
    SpanRecord,
    SpanStatus,
    StructuredLogRecord,
    current_telemetry_context,
    start_request_context,
)

from .common import ProblemDetail

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_CORRELATION_ID_RE = _REQUEST_ID_RE
_DEFAULT_SAMPLER = DeterministicSampler(normal_sample_rate=0.10)


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

        supplied_correlation_id = request.headers.get("X-Correlation-ID")
        correlation_id = (
            supplied_correlation_id
            if supplied_correlation_id is not None
            and _CORRELATION_ID_RE.fullmatch(supplied_correlation_id)
            else None
        )

        # Request/correlation/trace headers are telemetry metadata, not business
        # authorization or request validity. Invalid values are replaced/discarded
        # by the observability context rather than rejecting the business request.
        with start_request_context(
            request_id=request_id,
            correlation_id=correlation_id,
            traceparent=request.headers.get("traceparent"),
            tracestate=request.headers.get("tracestate"),
        ) as telemetry_context:
            request.state.telemetry_context = telemetry_context
            started_at = datetime.now(UTC)
            started_clock = perf_counter()
            try:
                response = await call_next(request)
            except Exception:
                ended_at = datetime.now(UTC)
                _record_http_telemetry(
                    request,
                    started_at=started_at,
                    ended_at=ended_at,
                    duration_ms=(perf_counter() - started_clock) * 1000,
                    status_code=500,
                    failed=True,
                )
                raise

            duration_ms = (perf_counter() - started_clock) * 1000
            ended_at = datetime.now(UTC)
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Correlation-ID"] = telemetry_context.correlation_id
            final_context = current_telemetry_context() or telemetry_context
            response.headers["traceparent"] = final_context.traceparent
            if final_context.tracestate:
                response.headers["tracestate"] = final_context.tracestate
            _record_http_telemetry(
                request,
                started_at=started_at,
                ended_at=ended_at,
                duration_ms=duration_ms,
                status_code=response.status_code,
                failed=response.status_code >= 500,
            )
            return response


def _telemetry(request: Request) -> SafeTelemetry:
    configured = getattr(request.app.state, "telemetry", None)
    if isinstance(configured, SafeTelemetry):
        return configured
    return SafeTelemetry(configured)


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    candidate = getattr(route, "path", None)
    return candidate if isinstance(candidate, str) and candidate else "unmatched"


def _record_http_telemetry(
    request: Request,
    *,
    started_at: datetime,
    ended_at: datetime,
    duration_ms: float,
    status_code: int,
    failed: bool,
) -> None:
    # Observability is never a business availability dependency. This entire block,
    # including validation/model construction, is best-effort.
    try:
        context = current_telemetry_context()
        if context is None:
            return
        route = _route_template(request)
        status_class = f"{status_code // 100}xx"
        telemetry = _telemetry(request)
        span_status = SpanStatus.ERROR if failed else SpanStatus.OK
        sampler = getattr(request.app.state, "telemetry_sampler", _DEFAULT_SAMPLER)
        decision = sampler.decide(
            trace_id=context.trace_id,
            span_status=span_status,
            log_level=LogLevel.ERROR if failed else LogLevel.INFO,
        )
        span_attributes: dict[str, str | int | float | bool] = {
            "http.method": request.method,
            "http.route": route,
            "http.status_code": status_code,
            "duration_ms": round(duration_ms, 3),
        }
        for key, value in (
            ("lumi.organization_id", context.organization_id),
            ("lumi.project_id", context.project_id),
            ("lumi.agent_run_id", context.agent_run_id),
            ("lumi.task_id", context.task_id),
            ("lumi.operation_id", context.operation_id),
            ("lumi.provider_request_id", context.provider_request_id),
        ):
            if value is not None:
                span_attributes[key] = str(value)
        if decision is SamplingDecision.RECORD_AND_SAMPLE:
            telemetry.record_span(
                SpanRecord(
                    name=f"HTTP {request.method} {route}",
                    trace_id=context.trace_id,
                    span_id=context.span_id,
                    parent_span_id=context.parent_span_id,
                    status=span_status,
                    started_at=started_at,
                    ended_at=ended_at,
                    attributes=span_attributes,
                )
            )
        telemetry.record_metric(
            MetricPoint(
                name="http.server.duration_ms",
                value=round(duration_ms, 3),
                unit="ms",
                recorded_at=ended_at,
                attributes={
                    "service": "lumi-api",
                    "http.method": request.method,
                    "http.route": route,
                    "http.status_class": status_class,
                    "outcome": "error" if failed else "success",
                },
            )
        )
        telemetry.emit_log(
            StructuredLogRecord(
                level=LogLevel.ERROR if failed else LogLevel.INFO,
                event="http.request.completed",
                message="HTTP request completed.",
                occurred_at=ended_at,
                trace_id=context.trace_id,
                span_id=context.span_id,
                request_id=context.request_id,
                correlation_id=context.correlation_id,
                fields={
                    "http.method": request.method,
                    "http.route": route,
                    "http.status_code": status_code,
                    "duration_ms": round(duration_ms, 3),
                },
            )
        )
    except Exception:
        return


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
