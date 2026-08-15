from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker

from lumi_api.auth.canonical_router import create_auth_router
from lumi_api.auth.notifications import RejectingAuthNotificationPort
from lumi_api.auth.smtp_notifications import SmtpAuthNotificationPort
from lumi_api.config import get_settings
from lumi_api.observability import ObservabilityConfig, apply_observability
from lumi_api.persistence.session import create_engine
from lumi_api.security import SecurityConfig, apply_security_hardening

settings = get_settings()
engine = create_engine()
session_factory = async_sessionmaker(engine, expire_on_commit=False)


def _origins() -> frozenset[str]:
    raw = os.environ.get("LUMI_ALLOWED_ORIGINS", "http://localhost:3000")
    return frozenset(item.strip().rstrip("/") for item in raw.split(",") if item.strip())


def _notifications():
    if settings.lumi_env in {"development", "test"}:
        return SmtpAuthNotificationPort(
            smtp_host=os.environ.get("AUTH_SMTP_HOST", "localhost"),
            smtp_port=int(os.environ.get("AUTH_SMTP_PORT", "1025")),
            from_address=os.environ.get("AUTH_FROM_ADDRESS", "no-reply@lumi.local"),
            public_base_url=os.environ.get("LUMI_PUBLIC_BASE_URL", "http://localhost:3000"),
            use_starttls=False,
        )
    return RejectingAuthNotificationPort()


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await engine.dispose()


app = FastAPI(
    title="LUMI Auth/Tenant Runtime",
    version=settings.lumi_version,
    lifespan=lifespan,
)
apply_security_hardening(
    app,
    SecurityConfig(production=settings.lumi_env == "production"),
)
apply_observability(
    app,
    ObservabilityConfig(service_name="lumi-auth-api", environment=settings.lumi_env),
)
app.include_router(
    create_auth_router(
        session_factory=session_factory,
        notifications=_notifications(),
        allowed_origins=_origins(),
        secure_cookie=settings.lumi_env not in {"development", "test"},
    )
)


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
