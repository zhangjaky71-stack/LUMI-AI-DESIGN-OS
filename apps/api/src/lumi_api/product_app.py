from __future__ import annotations

import os
from typing import cast

from fastapi import HTTPException
from sqlalchemy import text

from lumi_api.api.v1.services import ApiV1Gateway
from lumi_api.asset_app import app, session_factory, settings
from lumi_api.generations.gateway import GenerationRuntimeGateway
from lumi_api.tool_approval_control import (
    build_tool_approval_control_runtime,
    create_tool_approval_control_router,
    create_tool_approval_public_router,
)
from lumi_api.tool_audit_control import (
    build_tool_audit_control_runtime,
    create_tool_audit_control_router,
)
from lumi_api.tool_data_control import (
    build_tool_data_control_runtime,
    create_tool_data_control_router,
)
from lumi_api.tool_side_effect_control import (
    build_tool_side_effect_control_runtime,
    create_tool_side_effect_control_router,
)

base_gateway = cast(ApiV1Gateway, app.state.api_v1_gateway)
app.state.api_v1_gateway = GenerationRuntimeGateway(base_gateway, session_factory)
app.title = "LUMI Product Control Plane"
app.version = settings.lumi_version

_internal_controls_required = settings.lumi_env in {"staging", "production"}
_side_effect_secret_present = bool(os.getenv("LUMI_SIDE_EFFECT_CONTROL_AUTH_SECRET", ""))
if _internal_controls_required or _side_effect_secret_present:
    if not settings.database_url:
        raise RuntimeError("LUMI_DATABASE_URL_REQUIRED_FOR_SIDE_EFFECT_CONTROL")
    app.include_router(
        create_tool_side_effect_control_router(
            build_tool_side_effect_control_runtime(settings.database_url)
        )
    )
    app.state.tool_side_effect_control_enabled = True
else:
    app.state.tool_side_effect_control_enabled = False

_audit_secret_present = bool(os.getenv("LUMI_TOOL_AUDIT_AUTH_SECRET", ""))
if _internal_controls_required or _audit_secret_present:
    app.include_router(
        create_tool_audit_control_router(
            build_tool_audit_control_runtime(session_factory)
        )
    )
    app.state.tool_audit_control_enabled = True
else:
    app.state.tool_audit_control_enabled = False

_approval_secret_present = bool(os.getenv("LUMI_TOOL_APPROVAL_AUTH_SECRET", ""))
if _internal_controls_required or _approval_secret_present:
    app.include_router(
        create_tool_approval_control_router(
            build_tool_approval_control_runtime(session_factory)
        )
    )
    app.state.tool_approval_control_enabled = True
else:
    app.state.tool_approval_control_enabled = False

_data_secret_present = bool(os.getenv("LUMI_TOOL_DATA_AUTH_SECRET", ""))
if _internal_controls_required or _data_secret_present:
    app.include_router(
        create_tool_data_control_router(
            build_tool_data_control_runtime(session_factory)
        )
    )
    app.state.tool_data_control_enabled = True
else:
    app.state.tool_data_control_enabled = False

app.include_router(create_tool_approval_public_router(session_factory))


def _payload(status: str = "ok") -> dict[str, str]:
    return {"service": "api", "status": status, "version": settings.lumi_version}


@app.get("/health/live", tags=["health"])
def health_live() -> dict[str, str]:
    return _payload()


@app.get("/health/ready", tags=["health"])
async def health_ready() -> dict[str, str]:
    try:
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database dependency unavailable") from exc
    if _internal_controls_required and not app.state.tool_side_effect_control_enabled:
        raise HTTPException(status_code=503, detail="side-effect control plane unavailable")
    if _internal_controls_required and not app.state.tool_audit_control_enabled:
        raise HTTPException(status_code=503, detail="tool audit control plane unavailable")
    if _internal_controls_required and not app.state.tool_approval_control_enabled:
        raise HTTPException(status_code=503, detail="tool approval control plane unavailable")
    if _internal_controls_required and not app.state.tool_data_control_enabled:
        raise HTTPException(status_code=503, detail="tool data control plane unavailable")
    return _payload()


@app.get("/version", tags=["meta"])
def version() -> dict[str, str]:
    return _payload()
