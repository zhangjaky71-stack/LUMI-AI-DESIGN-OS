from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

from .core import (
    BoundedMetrics,
    ObservabilityConfig,
    bind_correlation,
    encode_log,
    new_correlation_context,
    reset_correlation,
    safe_log_record,
)

_LOGGER = logging.getLogger("lumi.observability")


def apply_observability(
    app: FastAPI,
    config: ObservabilityConfig,
    *,
    metrics: BoundedMetrics | None = None,
) -> BoundedMetrics:
    registry = metrics or BoundedMetrics()
    app.state.lumi_metrics = registry
    app.state.lumi_observability = config

    if config.metrics_enabled:

        async def metrics_endpoint() -> PlainTextResponse:
            return PlainTextResponse(
                registry.render_prometheus(),
                media_type="text/plain; version=0.0.4",
            )

        app.add_api_route(
            config.metrics_path,
            metrics_endpoint,
            methods=["GET"],
            include_in_schema=False,
        )

    @app.middleware("http")
    async def correlation_middleware(request: Request, call_next: Any):
        context = new_correlation_context(
            request_id=request.headers.get("x-request-id"),
            correlation_id=request.headers.get("x-correlation-id"),
            traceparent=request.headers.get("traceparent"),
        )
        token = bind_correlation(context)
        started = perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers.setdefault("X-Request-ID", context.request_id)
            response.headers.setdefault("X-Correlation-ID", context.correlation_id)
            response.headers.setdefault("traceparent", context.traceparent)
            return response
        except Exception as exc:
            if request.url.path != config.metrics_path:
                _emit(
                    config,
                    "ERROR",
                    "http.request.failed",
                    {
                        "error_type": type(exc).__name__,
                        "method": request.method,
                        "route": _route_template(request),
                    },
                )
            raise
        finally:
            if request.url.path != config.metrics_path:
                duration = max(perf_counter() - started, 0.0)
                route = _route_template(request)
                registry.observe_http(
                    method=request.method,
                    route=route,
                    status_code=status_code,
                    duration=duration,
                )
                _emit(
                    config,
                    "INFO" if status_code < 500 else "ERROR",
                    "http.request.completed",
                    {
                        "duration_ms": round(duration * 1000, 3),
                        "method": request.method,
                        "route": route,
                        "status_code": status_code,
                    },
                )
            reset_correlation(token)

    return registry


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) and path else "unmatched"


def _emit(
    config: ObservabilityConfig,
    level: str,
    event: str,
    fields: dict[str, Any],
) -> None:
    try:
        record = safe_log_record(
            level=level,
            service=config.service_name,
            environment=config.environment,
            event=event,
            fields=fields,
        )
        log_method = _LOGGER.error if level == "ERROR" else _LOGGER.info
        log_method(encode_log(record))
    except Exception:
        # Telemetry must never make the product path fail.
        return
