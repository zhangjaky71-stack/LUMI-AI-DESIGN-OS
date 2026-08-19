from __future__ import annotations

from typing import cast

from fastapi import HTTPException
from sqlalchemy import text

from lumi_api.api.v1.services import ApiV1Gateway
from lumi_api.asset_app import app, session_factory, settings
from lumi_api.generations.gateway import GenerationRuntimeGateway

base_gateway = cast(ApiV1Gateway, app.state.api_v1_gateway)
app.state.api_v1_gateway = GenerationRuntimeGateway(base_gateway, session_factory)
app.title = "LUMI Product Control Plane"
app.version = settings.lumi_version


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
    return _payload()


@app.get("/version", tags=["meta"])
def version() -> dict[str, str]:
    return _payload()
