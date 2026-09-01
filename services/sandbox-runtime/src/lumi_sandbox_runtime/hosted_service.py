from __future__ import annotations

import os

from fastapi import FastAPI

from .ecs_discovery import discover_remote_backend
from .service import HostedSandboxRuntime, create_sandbox_runtime_app


def create_runtime_app() -> FastAPI:
    secret = os.getenv("LUMI_SANDBOX_RUNTIME_AUTH_SECRET", "")
    if len(secret) < 32 or len(secret) > 8192 or "\x00" in secret:
        raise RuntimeError("LUMI_SANDBOX_RUNTIME_AUTH_SECRET_REQUIRED")
    return create_sandbox_runtime_app(
        HostedSandboxRuntime(
            environment=os.getenv("LUMI_ENV", os.getenv("LUMI_ENVIRONMENT", "unknown")),
            auth_secret=secret,
            backend=discover_remote_backend(),
        )
    )
