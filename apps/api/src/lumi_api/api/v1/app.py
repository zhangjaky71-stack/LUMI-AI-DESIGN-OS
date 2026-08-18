from __future__ import annotations

import os

from fastapi import Depends, FastAPI

from lumi_api.observability import DeterministicSampler, PythonJsonLoggingSink, SafeTelemetry
from lumi_api.security import install_http_security

from .admin_auth_guard import establish_platform_admin_identity
from .admin_routes import router as admin_router
from .agent_run_routes import router as agent_run_router
from .agent_workspace_routes import router as agent_workspace_router
from .approval_routes import router as approval_router
from .artifact_engine_routes import router as artifact_engine_router
from .asset_routes import router as asset_router
from .asset_intelligence_routes import router as asset_intelligence_router
from .auth_guard import enforce_api_auth
from .auth_routes import router as auth_router
from .billing_routes import router as billing_router
from .billing_routes import webhook_router as billing_webhook_router
from .brand_registry_routes import router as brand_registry_router
from .brand_rules_routes import router as brand_rules_router
from .canvas_document_routes import router as canvas_document_router
from .collaboration_routes import router as collaboration_router
from .cost_routes import router as cost_router
from .errors import install_error_contract
from .export_product_routes import router as export_product_router
from .governance_routes import router as governance_router
from .idempotency_middleware import IdempotencyReplayMiddleware
from .identity_engine_routes import router as identity_engine_router
from .image_edit_routes import router as image_edit_router
from .image_generation_routes import router as image_generation_router
from .routes import router
from .version_history_routes import router as version_history_router


def create_contract_app(*, environment: str | None = None) -> FastAPI:
    runtime_environment = (environment or os.getenv("LUMI_ENV", "development")).strip().casefold()
    expose_interactive_docs = runtime_environment != "production"
    app = FastAPI(
        title="LUMI AI Design OS API",
        version="1.0.0",
        docs_url="/api/docs" if expose_interactive_docs else None,
        redoc_url="/api/redoc" if expose_interactive_docs else None,
        openapi_url="/api/openapi.json" if expose_interactive_docs else None,
    )
    # Runtime environment is shared with the outer correlation/error boundary so
    # responses it creates directly keep the same production security-header policy.
    app.state.runtime_environment = runtime_environment
    # Logs have a safe standard-library JSON baseline immediately. Trace/metric
    # exporters are deliberately composed separately through an OTel/Collector port.
    app.state.telemetry = SafeTelemetry(PythonJsonLoggingSink())
    app.state.telemetry_sampler = DeterministicSampler(normal_sample_rate=0.10)
    # Install before the error contract so RequestIdMiddleware remains outside the
    # security gate and every security rejection receives the canonical request id.
    install_http_security(app, environment=runtime_environment)
    install_error_contract(app)
    app.add_middleware(IdempotencyReplayMiddleware)
    app.include_router(auth_router)
    app.include_router(billing_webhook_router)
    app.include_router(admin_router, dependencies=[Depends(establish_platform_admin_identity)])
    app.include_router(router, dependencies=[Depends(enforce_api_auth)])
    app.include_router(asset_router, dependencies=[Depends(enforce_api_auth)])
    app.include_router(asset_intelligence_router, dependencies=[Depends(enforce_api_auth)])
    app.include_router(cost_router, dependencies=[Depends(enforce_api_auth)])
    app.include_router(agent_run_router, dependencies=[Depends(enforce_api_auth)])
    app.include_router(agent_workspace_router, dependencies=[Depends(enforce_api_auth)])
    app.include_router(canvas_document_router, dependencies=[Depends(enforce_api_auth)])
    app.include_router(artifact_engine_router, dependencies=[Depends(enforce_api_auth)])
    app.include_router(version_history_router, dependencies=[Depends(enforce_api_auth)])
    app.include_router(export_product_router, dependencies=[Depends(enforce_api_auth)])
    app.include_router(collaboration_router, dependencies=[Depends(enforce_api_auth)])
    app.include_router(approval_router, dependencies=[Depends(enforce_api_auth)])
    app.include_router(billing_router, dependencies=[Depends(enforce_api_auth)])
    app.include_router(governance_router, dependencies=[Depends(enforce_api_auth)])
    app.include_router(brand_registry_router, dependencies=[Depends(enforce_api_auth)])
    app.include_router(brand_rules_router, dependencies=[Depends(enforce_api_auth)])
    app.include_router(identity_engine_router, dependencies=[Depends(enforce_api_auth)])
    app.include_router(image_generation_router, dependencies=[Depends(enforce_api_auth)])
    app.include_router(image_edit_router, dependencies=[Depends(enforce_api_auth)])
    return app


contract_app = create_contract_app()
