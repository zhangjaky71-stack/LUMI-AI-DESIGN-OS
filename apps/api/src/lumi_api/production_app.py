from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker

from lumi_api.api import create_contract_app
from lumi_api.api.v1.context import get_request_context
from lumi_api.assets.router import create_asset_storage_router
from lumi_api.assets.runtime import build_asset_storage_runtime
from lumi_api.auth.canonical_router import create_auth_router
from lumi_api.auth.notifications import RejectingAuthNotificationPort
from lumi_api.auth.smtp_notifications import SmtpAuthNotificationPort
from lumi_api.config import Settings, get_settings
from lumi_api.observability import ObservabilityConfig, apply_observability
from lumi_api.persistence.session import create_engine
from lumi_api.projects.gateway import ProjectCoreGateway
from lumi_api.projects.security import get_secure_project_context
from lumi_api.runtime_capabilities import (
    LAUNCH_REQUIRED_CAPABILITIES,
    RuntimeCapabilityRegistry,
    required_capabilities_for_environment,
)
from lumi_api.security import SecurityConfig, apply_security_hardening


def _origins() -> frozenset[str]:
    raw = os.environ.get("LUMI_ALLOWED_ORIGINS", "http://localhost:3000")
    return frozenset(item.strip().rstrip("/") for item in raw.split(",") if item.strip())


def _notifications(settings: Settings):
    if settings.lumi_env in {"development", "test"}:
        return SmtpAuthNotificationPort(
            smtp_host=os.environ.get("AUTH_SMTP_HOST", "localhost"),
            smtp_port=int(os.environ.get("AUTH_SMTP_PORT", "1025")),
            from_address=os.environ.get("AUTH_FROM_ADDRESS", "no-reply@lumi.local"),
            public_base_url=os.environ.get("LUMI_PUBLIC_BASE_URL", "http://localhost:3000"),
            use_starttls=False,
        )
    return RejectingAuthNotificationPort()


def _register_known_gaps(registry: RuntimeCapabilityRegistry) -> None:
    # Keep this list explicit until each existing domain/runtime implementation is
    # connected to the production composition root. These entries make missing
    # wiring visible to readiness instead of silently falling through to 501.
    gaps = {
        "artifact_versions": "ApiV1Gateway artifact methods still lack a production adapter.",
        "agent_runs": "Agent control plane is transport-neutral and not wired into this API runtime.",
        "tasks": "Task runtime is not wired into the production ApiV1Gateway.",
        "generation": "Generation runtime is not wired into the production ApiV1Gateway.",
        "approval": "Approval Router exists, but production-persistent ApprovalEngine wiring is not installed.",
        "billing": "Billing Router exists, but durable billing/payment-provider wiring is not installed.",
        "collaboration": "Collaboration Router exists, but production service/repository wiring is not installed.",
        "governance": "Governance Router exists, but production service/repository wiring is not installed.",
        "admin": "Admin Router exists, but production AdminConsoleService wiring is not installed.",
    }
    for name, reason in gaps.items():
        registry.missing(name, reason=reason)


def create_production_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    engine = create_engine(resolved)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    registry = RuntimeCapabilityRegistry(
        required=required_capabilities_for_environment(resolved.lumi_env)
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        await engine.dispose()

    app = create_contract_app(gateway=ProjectCoreGateway(session_factory))
    app.title = "LUMI AI Design OS Production API"
    app.version = resolved.lumi_version
    app.router.lifespan_context = lifespan
    app.state.project_session_factory = session_factory
    app.state.project_allowed_origins = _origins()
    app.state.runtime_capabilities = registry
    app.dependency_overrides[get_request_context] = get_secure_project_context

    registry.ready("projects", adapter="ProjectCoreGateway/SQLAlchemy")

    app.include_router(
        create_auth_router(
            session_factory=session_factory,
            notifications=_notifications(resolved),
            allowed_origins=_origins(),
            secure_cookie=resolved.lumi_env not in {"development", "test"},
        )
    )
    registry.ready("auth", adapter="CanonicalAuthRouter/SQLAlchemy")

    if resolved.s3_bucket:
        app.include_router(
            create_asset_storage_router(
                build_asset_storage_runtime(
                    settings=resolved,
                    session_factory=session_factory,
                )
            )
        )
        registry.ready("asset_upload", adapter="AssetStorageRuntime/S3")
    else:
        registry.missing("asset_upload", reason="S3_BUCKET is not configured.")

    _register_known_gaps(registry)

    @app.get("/health/live", tags=["health"])
    async def health_live() -> dict[str, str]:
        return {"status": "ok", "service": "lumi-production-api"}

    @app.get("/health/capabilities", tags=["health"])
    async def health_capabilities():
        snapshot = registry.snapshot()
        snapshot["environment"] = resolved.lumi_env
        snapshot["launch_required_capabilities"] = sorted(LAUNCH_REQUIRED_CAPABILITIES)
        return snapshot

    @app.get("/health/ready", tags=["health"])
    async def health_ready():
        database_ready = True
        database_error: str | None = None
        try:
            async with session_factory() as session:
                await session.execute(text("SELECT 1"))
        except (SQLAlchemyError, OSError, RuntimeError) as exc:
            database_ready = False
            database_error = exc.__class__.__name__

        missing = registry.missing_required
        ready = database_ready and not missing
        payload = {
            "status": "ready" if ready else "not_ready",
            "service": "lumi-production-api",
            "environment": resolved.lumi_env,
            "database_ready": database_ready,
            "missing_required_capabilities": list(missing),
        }
        if database_error is not None:
            payload["database_error"] = database_error
        if ready:
            return payload
        return JSONResponse(status_code=503, content=payload)

    apply_security_hardening(
        app,
        SecurityConfig(production=resolved.lumi_env == "production"),
    )
    apply_observability(
        app,
        ObservabilityConfig(service_name="lumi-production-api", environment=resolved.lumi_env),
    )
    return app
