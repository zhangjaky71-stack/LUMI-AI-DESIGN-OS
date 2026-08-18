from __future__ import annotations

from lumi_model_gateway import (
    CostTelemetrySink,
    LedgerBudgetGuard,
    ModelGateway,
    ModelGatewayAPI,
    ModelRouter,
    PaidInvocationGuard,
    PaidStreamGuard,
    ProviderHealthRegistry,
    ProviderRegistry,
    RetryPolicy,
)

from .costs import PostgresModelCostAccounting


class HostedModelGatewayConfigurationError(RuntimeError):
    code = "MODEL_GATEWAY_HOSTED_CONFIGURATION_INVALID"


def build_hosted_model_gateway(
    *,
    database_dsn: str,
    registry: ProviderRegistry,
    health: ProviderHealthRegistry,
    router: ModelRouter,
    paid_guard: PaidInvocationGuard,
    paid_stream_guard: PaidStreamGuard | None = None,
    telemetry: CostTelemetrySink | None = None,
    retry_policy: RetryPolicy | None = None,
) -> ModelGatewayAPI:
    """Production/Staging composition root for all paid provider capabilities.

    Provider adapters and NODE-20 paid-side-effect guards remain injected ports,
    but the financial boundary is intentionally *not* injectable here. Hosted
    execution always binds Model Gateway to NODE-27's PostgreSQL accounting via
    ``LedgerBudgetGuard(PostgresModelCostAccounting(...))``. This prevents an
    application image from accidentally falling back to request-local budgeting.
    """

    if not database_dsn or not database_dsn.strip():
        raise HostedModelGatewayConfigurationError(
            "hosted Model Gateway requires LUMI_DATABASE_URL for durable accounting"
        )

    accounting = PostgresModelCostAccounting(database_dsn)
    budget_guard = LedgerBudgetGuard(accounting)
    gateway = ModelGateway(
        registry=registry,
        health=health,
        router=router,
        paid_guard=paid_guard,
        paid_stream_guard=paid_stream_guard,
        budget_guard=budget_guard,
        telemetry=telemetry,
        retry_policy=retry_policy,
    )
    return ModelGatewayAPI(gateway)
