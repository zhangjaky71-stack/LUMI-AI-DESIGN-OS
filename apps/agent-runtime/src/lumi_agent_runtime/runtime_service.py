from __future__ import annotations

import asyncio
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from lumi_tool_gateway.http_transport import HttpToolGatewayTransport

from .deep_runtime.model_gateway_chat import HttpProfileModelProvider

_DEPENDENCY_TIMEOUT_SECONDS = 3.0
_REQUIRED_EXECUTION_BINDINGS = (
    "deep-agent-registry",
    "durable-checkpointer",
    "sandbox-backend",
    "graph-control-plane",
)


@dataclass(frozen=True, slots=True)
class HostedAgentRuntimeState:
    environment: str
    database_url: str
    model_gateway_url: str
    tool_gateway_url: str
    model_provider: HttpProfileModelProvider
    tool_gateway: HttpToolGatewayTransport
    execution_bindings: frozenset[str]

    @property
    def missing_execution_bindings(self) -> tuple[str, ...]:
        return tuple(
            binding
            for binding in _REQUIRED_EXECUTION_BINDINGS
            if binding not in self.execution_bindings
        )


def create_runtime_app() -> FastAPI:
    database_url = _required_env("LUMI_DATABASE_URL", max_length=8192)
    model_gateway_url = _required_service_url("LUMI_MODEL_GATEWAY_URL")
    tool_gateway_url = _required_service_url("LUMI_TOOL_GATEWAY_URL")
    model_provider = HttpProfileModelProvider.from_env()
    tool_gateway = HttpToolGatewayTransport(
        base_url=tool_gateway_url,
        auth_secret=_required_env("LUMI_TOOL_GATEWAY_AUTH_SECRET", max_length=8192),
        service="agent-runtime",
    )
    state = HostedAgentRuntimeState(
        environment=os.getenv("LUMI_ENV", os.getenv("LUMI_ENVIRONMENT", "unknown")),
        database_url=database_url,
        model_gateway_url=model_gateway_url,
        tool_gateway_url=tool_gateway_url,
        model_provider=model_provider,
        tool_gateway=tool_gateway,
        # Fail closed until the production registry/checkpointer/sandbox/control-plane
        # composition is actually installed. Never substitute test doubles here.
        execution_bindings=frozenset(),
    )
    return create_agent_runtime_app(state)


def create_agent_runtime_app(state: HostedAgentRuntimeState) -> FastAPI:
    app = FastAPI(
        title="LUMI Agent Runtime",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.get("/health/live", tags=["health"])
    async def health_live() -> dict[str, Any]:
        return _base_health(state, status="ok")

    @app.get("/health/ready", tags=["health"])
    async def health_ready() -> JSONResponse:
        dependency_results = await asyncio.gather(
            _probe_ready(state.model_gateway_url),
            _probe_ready(state.tool_gateway_url),
        )
        dependency_status = {
            "model-gateway": dependency_results[0],
            "tool-gateway": dependency_results[1],
        }
        missing = state.missing_execution_bindings
        ready = not missing and all(dependency_status.values())
        return JSONResponse(
            status_code=200 if ready else 503,
            content={
                **_base_health(state, status="ok" if ready else "not_ready"),
                "dependencies": dependency_status,
                "missing_execution_bindings": list(missing),
            },
        )

    @app.get("/version", tags=["meta"])
    async def version() -> dict[str, Any]:
        return {
            **_base_health(state, status="ok"),
            "model_boundary": "private-model-gateway",
            "tool_boundary": "private-tool-gateway",
            "local_provider_credentials": False,
            "host_local_tools": False,
        }

    return app


def _base_health(state: HostedAgentRuntimeState, *, status: str) -> dict[str, Any]:
    return {
        "service": "agent-runtime",
        "status": status,
        "environment": state.environment,
        "execution_binding_count": len(state.execution_bindings),
    }


async def _probe_ready(base_url: str) -> bool:
    return await asyncio.to_thread(_probe_ready_sync, base_url)


def _probe_ready_sync(base_url: str) -> bool:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/health/ready",
        headers={"Accept": "application/json", "User-Agent": "LUMI-AgentRuntime/1.0"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=_DEPENDENCY_TIMEOUT_SECONDS) as response:
            response.read(4096)
            return 200 <= int(response.status) < 300
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
        return False


def _required_env(name: str, *, max_length: int) -> str:
    value = os.getenv(name, "")
    if not value or len(value) > max_length or "\x00" in value:
        raise RuntimeError(f"{name}_REQUIRED")
    return value


def _required_service_url(name: str) -> str:
    value = _required_env(name, max_length=2048).rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise RuntimeError(f"{name}_INVALID")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RuntimeError(f"{name}_INVALID")
    return value
