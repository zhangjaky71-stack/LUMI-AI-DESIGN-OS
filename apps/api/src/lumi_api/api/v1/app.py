from __future__ import annotations

from fastapi import Depends, FastAPI

from .agent_run_routes import router as agent_run_router
from .artifact_engine_routes import router as artifact_engine_router
from .asset_routes import router as asset_router
from .auth_guard import enforce_api_auth
from .auth_routes import router as auth_router
from .brand_rules_routes import router as brand_rules_router
from .cost_routes import router as cost_router
from .errors import install_error_contract
from .idempotency_middleware import IdempotencyReplayMiddleware
from .routes import router


def create_contract_app() -> FastAPI:
    app = FastAPI(
        title="LUMI AI Design OS API",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )
    install_error_contract(app)
    app.add_middleware(IdempotencyReplayMiddleware)
    app.include_router(auth_router)
    app.include_router(router, dependencies=[Depends(enforce_api_auth)])
    app.include_router(asset_router, dependencies=[Depends(enforce_api_auth)])
    app.include_router(cost_router, dependencies=[Depends(enforce_api_auth)])
    app.include_router(agent_run_router, dependencies=[Depends(enforce_api_auth)])
    app.include_router(artifact_engine_router, dependencies=[Depends(enforce_api_auth)])
    app.include_router(brand_rules_router, dependencies=[Depends(enforce_api_auth)])
    return app


contract_app = create_contract_app()
