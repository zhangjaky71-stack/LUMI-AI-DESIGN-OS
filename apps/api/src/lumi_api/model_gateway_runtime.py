from __future__ import annotations

from lumi_model_gateway import (
    CostTelemetrySink,
    LedgerBudgetGuard,
    ModelGateway,
    ModelGatewayAPI,
    ModelRouter,
    ProviderHealthRegistry,
    ProviderRegistry,
    RetryPolicy,
)

from .costs import PostgresModelCostAccounting
from .model_paid_guard import PostgresModelPaidInvocationGuard


class HostedModelGatewayConfigurationError(RuntimeError):
    code = "MODEL_GATEWAY_HOSTED_CONFIGURATION_INVALID"


def build_hosted_model_gateway(
    *,
    database_dsn: str,
    registry: ProviderRegistry,
    health: ProviderHealthRegistry,
    router: ModelRouter,
    telemetry: CostTelemetrySink | None = None,
    retry_policy: RetryPolicy | None = None,
) -> ModelGatewayAPI:
    """Production/Staging composition root for paid provider capabilities.

    Hosted execution owns both durable financial and paid-side-effect safety
    boundaries. Callers cannot replace NODE-27 accounting or NODE-20's paid
    invocation guard with request-local/in-memory implementations.

    Streaming is intentionally fail-closed here because a durable PostgreSQL
    paid-stream guard has not yet been implemented. ModelGateway therefore gets
    no ``paid_stream_guard`` from the hosted composition root.
    """

    if not database_dsn or not database_dsn.strip():
        raise HostedModelGatewayConfigurationError(
            "hosted Model Gateway requires LUMI_DATABASE_URL for durable accounting"
        )

    accounting = PostgresModelCostAccounting(database_dsn)
    budget_guard = LedgerBudgetGuard(accounting)
    paid_guard = PostgresModelPaidInvocationGuard(database_dsn)
    gateway = ModelGateway(
        registry=registry,
        health=health,
        router=router,
        paid_guard=paid_guard,
        budget_guard=budget_guard,
        telemetry=telemetry,
        retry_policy=retry_policy,
    )
    return ModelGatewayAPI(gateway)
