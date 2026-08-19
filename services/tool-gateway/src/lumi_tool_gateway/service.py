from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .api import ToolGatewayAPI
from .approval_control import HttpApprovalResolver
from .audit_control import HttpAuditSink
from .catalog import build_p0_registry
from .errors import (
    ToolAmbiguousSideEffectError,
    ToolApprovalControlUnavailableError,
    ToolAuditUnavailableError,
    ToolDisabledError,
    ToolGatewayError,
    ToolIdempotencyConflictError,
    ToolIdempotencyInProgressError,
    ToolInputValidationError,
    ToolNotFoundError,
    ToolPermissionDeniedError,
    ToolPriorSideEffectFailedError,
    ToolSideEffectControlUnavailableError,
    ToolVersionError,
)
from .gateway import ToolGateway
from .http_transport import (
    AUTH_SERVICE_HEADER,
    AUTH_SIGNATURE_HEADER,
    AUTH_TIMESTAMP_HEADER,
    INVOKE_PATH,
    InternalToolGatewayAuthError,
    decode_tool_request,
    encode_tool_result,
    verify_internal_request,
)
from .native import SandboxExecuteAdapter
from .ports import ToolAdapter
from .sandbox_transport import HttpSandboxExecutor
from .side_effect_control import HttpSideEffectControlClient, RemoteSideEffectGuard

_ALLOWED_CALLERS = frozenset({"agent-runtime"})
_MAX_BODY_BYTES = 2 * 1024 * 1024
_REQUIRED_RUNTIME_BINDINGS = frozenset(
    {
        "approval-resolver",
        "audit-sink",
        "result-offloader",
        "side-effect-guard",
    }
)


@dataclass(frozen=True, slots=True)
class ToolGatewayServiceRuntime:
    api: ToolGatewayAPI
    auth_secret: str
    environment: str
    tool_count: int
    adapter_keys: frozenset[str]
    required_adapter_keys: frozenset[str]
    runtime_bindings: frozenset[str]

    @property
    def missing_adapter_keys(self) -> tuple[str, ...]:
        return tuple(sorted(self.required_adapter_keys - self.adapter_keys))

    @property
    def missing_runtime_bindings(self) -> tuple[str, ...]:
        return tuple(sorted(_REQUIRED_RUNTIME_BINDINGS - self.runtime_bindings))


def create_runtime_app() -> FastAPI:
    auth_secret = _required_env("LUMI_TOOL_GATEWAY_AUTH_SECRET", max_length=8192)
    environment = os.getenv("LUMI_ENV", os.getenv("LUMI_ENVIRONMENT", "unknown"))
    registry = build_p0_registry()
    adapters = _build_hosted_adapters()
    required = frozenset(definition.key for definition in registry.definitions() if definition.enabled)
    approval_resolver = HttpApprovalResolver.from_env()
    side_effect_guard = RemoteSideEffectGuard(HttpSideEffectControlClient.from_env())
    audit_sink = HttpAuditSink.from_env()
    gateway = ToolGateway(
        registry=registry,
        adapters=adapters,
        approval_resolver=approval_resolver,
        side_effect_guard=side_effect_guard,
        audit_sink=audit_sink,
    )
    return create_tool_gateway_app(
        ToolGatewayServiceRuntime(
            api=ToolGatewayAPI(gateway),
            auth_secret=auth_secret,
            environment=environment,
            tool_count=len(registry.definitions()),
            adapter_keys=frozenset(adapters),
            required_adapter_keys=required,
            runtime_bindings=frozenset(
                {"approval-resolver", "side-effect-guard", "audit-sink"}
            ),
        )
    )


def create_tool_gateway_app(runtime: ToolGatewayServiceRuntime) -> FastAPI:
    app = FastAPI(
        title="LUMI Tool Gateway",
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
        missing_adapters = runtime.missing_adapter_keys
        missing_bindings = runtime.missing_runtime_bindings
        ready = not missing_adapters and not missing_bindings
        return JSONResponse(
            status_code=200 if ready else 503,
            content={
                **_health_payload(runtime, status="ok" if ready else "not_ready"),
                "missing_adapters": list(missing_adapters),
                "missing_runtime_bindings": list(missing_bindings),
            },
        )

    @app.get("/version", tags=["meta"])
    async def version() -> dict[str, Any]:
        return _health_payload(runtime, status="ok")

    @app.post(INVOKE_PATH, tags=["internal"])
    async def invoke(request: Request) -> JSONResponse:
        decoded = await _decode_internal_tool_request(request, runtime)
        if isinstance(decoded, JSONResponse):
            return decoded
        if runtime.missing_runtime_bindings:
            return _error(
                503,
                "TOOL_GATEWAY_RUNTIME_NOT_READY",
                "Tool Gateway production bindings are incomplete",
            )
        try:
            result = await runtime.api.invoke(decoded)
        except ToolPermissionDeniedError as exc:
            return _error(403, exc.code, str(exc))
        except (ToolNotFoundError, ToolVersionError, ToolDisabledError) as exc:
            return _error(404, exc.code, str(exc))
        except ToolIdempotencyInProgressError as exc:
            return _error(425, exc.code, str(exc))
        except (ToolIdempotencyConflictError, ToolPriorSideEffectFailedError) as exc:
            return _error(409, exc.code, str(exc))
        except (
            ToolAmbiguousSideEffectError,
            ToolApprovalControlUnavailableError,
            ToolAuditUnavailableError,
            ToolSideEffectControlUnavailableError,
        ) as exc:
            return _error(503, exc.code, str(exc))
        except ToolInputValidationError as exc:
            return _error(422, exc.code, str(exc))
        except ToolGatewayError as exc:
            message = str(exc)
            status = 503 if message.startswith("TOOL_ADAPTER_NOT_REGISTERED:") else 422
            return _error(status, exc.code, message)
        except Exception:
            return _error(
                500,
                "TOOL_GATEWAY_INTERNAL_ERROR",
                "internal Tool Gateway failure",
            )
        return JSONResponse(status_code=200, content=encode_tool_result(result))

    return app


async def _decode_internal_tool_request(
    request: Request,
    runtime: ToolGatewayServiceRuntime,
):
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            parsed_length = int(content_length)
        except ValueError:
            return _error(400, "TOOL_GATEWAY_CONTENT_LENGTH_INVALID", "invalid content length")
        if parsed_length < 0 or parsed_length > _MAX_BODY_BYTES:
            return _error(413, "TOOL_GATEWAY_REQUEST_TOO_LARGE", "request body is too large")
    body = await request.body()
    if len(body) > _MAX_BODY_BYTES:
        return _error(413, "TOOL_GATEWAY_REQUEST_TOO_LARGE", "request body is too large")
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
    except InternalToolGatewayAuthError as exc:
        return _error(401, str(exc), "internal Tool Gateway authentication failed")
    try:
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("TOOL_GATEWAY_HTTP_REQUEST_OBJECT_REQUIRED")
        return decode_tool_request(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return _error(422, "TOOL_GATEWAY_REQUEST_INVALID", str(exc))


def _build_hosted_adapters() -> dict[str, ToolAdapter]:
    """Production adapter composition point.

    Only adapters backed by real downstream runtime boundaries may be registered here.
    Missing tools keep readiness blocked; no placeholder/no-op adapters are permitted.
    """
    return {
        "sandbox.execute@1.0.0": SandboxExecuteAdapter(HttpSandboxExecutor.from_env()),
    }


def _health_payload(runtime: ToolGatewayServiceRuntime, *, status: str) -> dict[str, Any]:
    return {
        "service": "tool-gateway",
        "status": status,
        "environment": runtime.environment,
        "tool_count": runtime.tool_count,
        "adapter_count": len(runtime.adapter_keys),
        "runtime_binding_count": len(runtime.runtime_bindings),
    }


def _required_env(name: str, *, max_length: int) -> str:
    value = os.getenv(name, "")
    if not value or len(value) > max_length or "\x00" in value:
        raise RuntimeError(f"{name}_REQUIRED")
    return value


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"code": code[:128], "message": message[:2000]},
    )
