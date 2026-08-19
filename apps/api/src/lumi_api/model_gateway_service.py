from __future__ import annotations

import json
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import asyncpg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from lumi_model_gateway import (
    BudgetExceededError,
    ModelGatewayAPI,
    ModelGatewayError,
    NoRouteError,
    PaidInvocationGuardRequiredError,
    ProviderInvocationError,
)
from lumi_model_gateway.estimate_transport import encode_route_candidate
from lumi_model_gateway.http_transport import (
    AUTH_SERVICE_HEADER,
    AUTH_SIGNATURE_HEADER,
    AUTH_TIMESTAMP_HEADER,
    InternalModelGatewayAuthError,
    decode_model_request,
    encode_model_result,
    verify_internal_request,
)
from lumi_model_gateway.models import ModelRequest

from .model_gateway_bootstrap import build_hosted_model_gateway_from_secret
from .provider_output_store import S3ProviderOutputStore

_INVOKE_PATH = "/internal/v1/models/invoke"
_ESTIMATE_PATH = "/internal/v1/models/estimate"
_ALLOWED_CALLERS = frozenset({"agent-runtime", "worker-media"})
_MAX_BODY_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ModelGatewayServiceRuntime:
    api: ModelGatewayAPI
    database_dsn: str
    auth_secret: str
    provider_count: int
    model_count: int
    environment: str


def create_runtime_app() -> FastAPI:
    database_dsn = _required_env("LUMI_DATABASE_URL", max_length=8192)
    auth_secret = _required_env("LUMI_MODEL_GATEWAY_AUTH_SECRET", max_length=8192)
    provider_secret = _required_env("LUMI_MODEL_PROVIDER_SECRET", max_length=262_144)
    media_provider_secret = _required_env(
        "LUMI_MEDIA_PROVIDER_SECRET",
        max_length=262_144,
    )
    environment = os.getenv("LUMI_ENV", os.getenv("LUMI_ENVIRONMENT", "unknown"))
    bootstrap = build_hosted_model_gateway_from_secret(
        database_dsn=database_dsn,
        provider_secret=provider_secret,
        media_provider_secret=media_provider_secret,
        provider_output_store=S3ProviderOutputStore.from_env(),
    )
    return create_model_gateway_app(
        ModelGatewayServiceRuntime(
            api=bootstrap.api,
            database_dsn=database_dsn,
            auth_secret=auth_secret,
            provider_count=bootstrap.provider_count,
            model_count=bootstrap.model_count,
            environment=environment,
        )
    )


def create_model_gateway_app(runtime: ModelGatewayServiceRuntime) -> FastAPI:
    app = FastAPI(
        title="LUMI Model Gateway",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.get("/health/live", tags=["health"])
    async def health_live() -> dict[str, Any]:
        return _health_payload(runtime, status="ok")

    @app.get("/health/ready", tags=["health"])
    async def health_ready() -> JSONResponse:
        ready, detail = await _database_ready(runtime.database_dsn)
        status = "ok" if ready else "not_ready"
        return JSONResponse(
            status_code=200 if ready else 503,
            content={**_health_payload(runtime, status=status), "database": detail},
        )

    @app.get("/version", tags=["meta"])
    async def version() -> dict[str, Any]:
        return _health_payload(runtime, status="ok")

    @app.post(_ESTIMATE_PATH, tags=["internal"])
    async def estimate(request: Request) -> JSONResponse:
        decoded = await _decode_internal_model_request(request, runtime)
        if isinstance(decoded, JSONResponse):
            return decoded
        try:
            candidate = await runtime.api.estimate(decoded)
        except NoRouteError as exc:
            return _error(503, exc.code, str(exc))
        except ModelGatewayError as exc:
            return _error(503, exc.code, str(exc))
        except Exception:
            return _error(
                500,
                "MODEL_GATEWAY_ESTIMATE_INTERNAL_ERROR",
                "internal model gateway estimate failure",
            )
        return JSONResponse(status_code=200, content=encode_route_candidate(candidate))

    @app.post(_INVOKE_PATH, tags=["internal"])
    async def invoke(request: Request) -> JSONResponse:
        decoded = await _decode_internal_model_request(request, runtime)
        if isinstance(decoded, JSONResponse):
            return decoded
        try:
            result = await runtime.api.invoke(decoded)
        except BudgetExceededError as exc:
            return _error(402, exc.code, str(exc))
        except NoRouteError as exc:
            return _error(503, exc.code, str(exc))
        except PaidInvocationGuardRequiredError as exc:
            return _error(503, exc.code, str(exc))
        except ProviderInvocationError as exc:
            status = 422 if exc.category.value in {
                "INVALID_REQUEST",
                "HARD_CONSTRAINT_INVALID",
                "USER_CONTENT_POLICY_BLOCK",
            } else 503
            return JSONResponse(
                status_code=status,
                content={
                    "code": exc.category.value,
                    "message": str(exc),
                    "provider": exc.provider,
                    "model": exc.model,
                    "delivery_state": exc.delivery_state.value,
                    "retry_after_seconds": exc.retry_after_seconds,
                },
            )
        except ModelGatewayError as exc:
            return _error(503, exc.code, str(exc))
        except Exception:
            return _error(
                500,
                "MODEL_GATEWAY_INTERNAL_ERROR",
                "internal model gateway failure",
            )
        return JSONResponse(status_code=200, content=encode_model_result(result))

    return app


async def _decode_internal_model_request(
    request: Request,
    runtime: ModelGatewayServiceRuntime,
) -> ModelRequest | JSONResponse:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            parsed_length = int(content_length)
        except ValueError:
            return _error(
                400,
                "MODEL_GATEWAY_CONTENT_LENGTH_INVALID",
                "invalid content length",
            )
        if parsed_length < 0 or parsed_length > _MAX_BODY_BYTES:
            return _error(
                413,
                "MODEL_GATEWAY_REQUEST_TOO_LARGE",
                "request body is too large",
            )
    body = await request.body()
    if len(body) > _MAX_BODY_BYTES:
        return _error(
            413,
            "MODEL_GATEWAY_REQUEST_TOO_LARGE",
            "request body is too large",
        )
    try:
        verify_internal_request(
            secret=runtime.auth_secret,
            allowed_services=_ALLOWED_CALLERS,
            method=request.method,
            path=request.url.path,
            body=body,
            service=request.headers.get(AUTH_SERVICE_HEADER),
            timestamp=request.headers.get(AUTH_TIMESTAMP_HEADER),
            signature=request.headers.get(AUTH_SIGNATURE_HEADER),
        )
    except InternalModelGatewayAuthError as exc:
        return _error(
            401,
            str(exc),
            "internal model gateway authentication failed",
        )
    try:
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("MODEL_GATEWAY_HTTP_REQUEST_OBJECT_REQUIRED")
        return decode_model_request(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return _error(422, "MODEL_GATEWAY_REQUEST_INVALID", str(exc))


def _health_payload(runtime: ModelGatewayServiceRuntime, *, status: str) -> dict[str, Any]:
    return {
        "service": "model-gateway",
        "status": status,
        "environment": runtime.environment,
        "provider_count": runtime.provider_count,
        "model_count": runtime.model_count,
    }


async def _database_ready(database_dsn: str) -> tuple[bool, str]:
    dsn = database_dsn.replace("postgresql+asyncpg://", "postgresql://", 1)
    connection: asyncpg.Connection | None = None
    try:
        connection = await asyncpg.connect(dsn, timeout=3.0)
        barrier_exists = await connection.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'idempotency_operations'
                  AND column_name = 'provider_attempt_started_at'
            )
            """
        )
        if not barrier_exists:
            return False, "provider_attempt_barrier_missing"
        policy = await connection.fetchrow(
            """
            SELECT daily_cap_usd, enabled, fail_closed, currency, window
            FROM platform_provider_cost_guard
            WHERE policy_key = 'platform'
            """
        )
        if policy is None:
            return False, "platform_provider_cost_guard_missing"
        cap = Decimal(str(policy["daily_cap_usd"]))
        if (
            policy["enabled"] is not True
            or policy["fail_closed"] is not True
            or policy["currency"] != "USD"
            or policy["window"] != "UTC_DAY"
            or cap <= 0
            or cap > Decimal("100.00000000")
        ):
            return False, "platform_provider_cost_guard_invalid"
        return True, "ok"
    except Exception:
        return False, "database_guard_check_failed"
    finally:
        if connection is not None:
            await connection.close()


def _required_env(name: str, *, max_length: int) -> str:
    value = os.getenv(name, "")
    if not value or len(value) > max_length or "\x00" in value:
        raise RuntimeError(f"{name}_REQUIRED")
    return value


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"code": code, "message": message[:2000]},
    )
