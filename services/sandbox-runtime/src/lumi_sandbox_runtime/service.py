from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import asdict, dataclass
from typing import Any
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .models import ExecRequest, NetworkPolicy, SandboxSpec
from .ports import SandboxBackend

_AUTH_SERVICE_HEADER = "X-Lumi-Service"
_AUTH_TIMESTAMP_HEADER = "X-Lumi-Timestamp"
_AUTH_SIGNATURE_HEADER = "X-Lumi-Signature"
_EXECUTE_PATH = "/internal/v1/sandbox/execute"
_ALLOWED_CALLERS = frozenset({"tool-gateway"})
_MAX_SKEW_SECONDS = 90
_MAX_BODY_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class HostedSandboxRuntime:
    environment: str
    auth_secret: str
    backend: SandboxBackend | None

    @property
    def ready(self) -> bool:
        return self.backend is not None


def create_runtime_app() -> FastAPI:
    return create_sandbox_runtime_app(
        HostedSandboxRuntime(
            environment=os.getenv("LUMI_ENV", os.getenv("LUMI_ENVIRONMENT", "unknown")),
            auth_secret=_required_secret("LUMI_SANDBOX_RUNTIME_AUTH_SECRET"),
            # Production must install a remote/isolation backend explicitly. LocalBackend
            # and DockerBackend are not valid Fargate composition shortcuts.
            backend=_build_production_backend(),
        )
    )


def create_sandbox_runtime_app(runtime: HostedSandboxRuntime) -> FastAPI:
    app = FastAPI(
        title="LUMI Sandbox Runtime",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.get("/health/live", tags=["health"])
    async def health_live() -> dict[str, Any]:
        return _health(runtime, status="ok")

    @app.get("/health/ready", tags=["health"])
    async def health_ready() -> JSONResponse:
        return JSONResponse(
            status_code=200 if runtime.ready else 503,
            content={
                **_health(runtime, status="ok" if runtime.ready else "not_ready"),
                "missing_bindings": [] if runtime.ready else ["remote-sandbox-provider"],
            },
        )

    @app.get("/version", tags=["meta"])
    async def version() -> dict[str, Any]:
        return {
            **_health(runtime, status="ok"),
            "network_default": NetworkPolicy.NONE.value,
            "host_docker_socket": False,
            "host_subprocess": False,
            "public_egress": False,
        }

    @app.post(_EXECUTE_PATH, tags=["internal"])
    async def execute(request: Request) -> JSONResponse:
        body_or_error = await _authenticated_body(request, runtime.auth_secret)
        if isinstance(body_or_error, JSONResponse):
            return body_or_error
        if runtime.backend is None:
            return _error(
                503,
                "SANDBOX_REMOTE_PROVIDER_UNAVAILABLE",
                "production sandbox provider is not configured",
            )
        try:
            payload = json.loads(body_or_error.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("SANDBOX_REQUEST_OBJECT_REQUIRED")
            organization_id = UUID(_required_string(payload, "organization_id"))
            agent_run_id = UUID(_required_string(payload, "agent_run_id"))
            command_raw = payload.get("command")
            if (
                not isinstance(command_raw, list)
                or not command_raw
                or len(command_raw) > 128
                or not all(isinstance(item, str) and item for item in command_raw)
            ):
                raise ValueError("SANDBOX_COMMAND_INVALID")
            timeout_raw = payload.get("timeout_seconds", 120)
            if isinstance(timeout_raw, bool) or not isinstance(timeout_raw, int):
                raise ValueError("SANDBOX_EXEC_TIMEOUT_INVALID")
            spec = SandboxSpec(
                organization_id=organization_id,
                agent_run_id=agent_run_id,
                timeout_seconds=timeout_raw,
                network_policy=NetworkPolicy.NONE,
            )
            exec_request = ExecRequest(tuple(command_raw), timeout_seconds=timeout_raw)
        except (ValueError, TypeError) as exc:
            return _error(422, "SANDBOX_REQUEST_INVALID", str(exc))

        sandbox_id: UUID | None = None
        try:
            sandbox_id = runtime.backend.create(spec)
            result = runtime.backend.exec(sandbox_id, exec_request)
            return JSONResponse(
                status_code=200,
                content={
                    "sandbox_id": str(sandbox_id),
                    **asdict(result),
                },
            )
        except Exception:
            return _error(500, "SANDBOX_EXECUTION_FAILED", "sandbox execution failed")
        finally:
            if sandbox_id is not None:
                try:
                    runtime.backend.terminate(sandbox_id)
                except Exception:
                    pass

    return app


async def _authenticated_body(request: Request, secret: str) -> bytes | JSONResponse:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            parsed = int(content_length)
        except ValueError:
            return _error(400, "SANDBOX_CONTENT_LENGTH_INVALID", "invalid content length")
        if parsed < 0 or parsed > _MAX_BODY_BYTES:
            return _error(413, "SANDBOX_REQUEST_TOO_LARGE", "request body is too large")
    body = await request.body()
    if len(body) > _MAX_BODY_BYTES:
        return _error(413, "SANDBOX_REQUEST_TOO_LARGE", "request body is too large")
    service = request.headers.get(_AUTH_SERVICE_HEADER)
    timestamp_raw = request.headers.get(_AUTH_TIMESTAMP_HEADER)
    signature = request.headers.get(_AUTH_SIGNATURE_HEADER)
    if service not in _ALLOWED_CALLERS:
        return _error(401, "SANDBOX_CALLER_FORBIDDEN", "sandbox authentication failed")
    try:
        timestamp = int(timestamp_raw or "")
    except ValueError:
        return _error(401, "SANDBOX_AUTH_TIMESTAMP_INVALID", "sandbox authentication failed")
    if abs(int(time.time()) - timestamp) > _MAX_SKEW_SECONDS:
        return _error(401, "SANDBOX_AUTH_TIMESTAMP_EXPIRED", "sandbox authentication failed")
    if signature is None or len(signature) != 64:
        return _error(401, "SANDBOX_AUTH_SIGNATURE_INVALID", "sandbox authentication failed")
    message = _auth_message(service, timestamp, request.method, request.url.path, body)
    expected = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature.lower(), expected):
        return _error(401, "SANDBOX_AUTH_SIGNATURE_INVALID", "sandbox authentication failed")
    return body


def _auth_message(service: str, timestamp: int, method: str, path: str, body: bytes) -> bytes:
    body_hash = hashlib.sha256(body).hexdigest()
    return f"{service}\n{timestamp}\n{method.upper()}\n{path}\n{body_hash}".encode("utf-8")


def _build_production_backend() -> SandboxBackend | None:
    """Production composition point; local process/Docker backends are forbidden here."""
    return None


def _health(runtime: HostedSandboxRuntime, *, status: str) -> dict[str, Any]:
    return {
        "service": "sandbox-runtime",
        "status": status,
        "environment": runtime.environment,
        "backend_bound": runtime.backend is not None,
    }


def _required_secret(name: str) -> str:
    value = os.getenv(name, "")
    if len(value) < 32 or len(value) > 8192 or "\x00" in value:
        raise RuntimeError(f"{name}_REQUIRED")
    return value


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"SANDBOX_FIELD_INVALID:{key}")
    return value


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"code": code[:128], "message": message[:2000]},
    )
