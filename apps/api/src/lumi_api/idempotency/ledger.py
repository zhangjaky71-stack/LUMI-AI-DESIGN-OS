from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg
from lumi_domain import new_uuid7


class LedgerConflictError(RuntimeError):
    code = "COST_LEDGER_OPERATION_REUSED_WITH_DIFFERENT_ENTRY"


@dataclass(frozen=True, slots=True)
class CostLedgerEntry:
    """NODE-20 compatibility contract over the NODE-27 evolved cost_ledger table."""

    organization_id: UUID
    operation_id: UUID
    entry_type: str
    amount: Decimal
    currency: str
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    project_id: UUID | None = None
    task_id: UUID | None = None
    agent_run_id: UUID | None = None
    generation_id: UUID | None = None
    provider_request_id: UUID | None = None
    reverses_entry_id: UUID | None = None
    provider: str | None = None
    model: str | None = None
    quantity: Decimal | None = None
    unit: str | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)
    entry_key: str = "primary"
    pricing_snapshot_id: str | None = None
    external_provider_request_id: str | None = None
    confidence: str = "unknown"
    cost_basis: str = "provider_cost"
    source: str = "node20_compat"

    def __post_init__(self) -> None:
        if not self.entry_type or len(self.entry_type) > 64:
            raise ValueError("COST_LEDGER_ENTRY_TYPE_INVALID")
        if not self.entry_key or len(self.entry_key) > 128:
            raise ValueError("COST_LEDGER_ENTRY_KEY_INVALID")
        if len(self.currency) != 3 or self.currency != self.currency.upper():
            raise ValueError("COST_LEDGER_CURRENCY_INVALID")
        if self.occurred_at.tzinfo is None:
            raise ValueError("COST_LEDGER_OCCURRED_AT_TZ_REQUIRED")
        if self.quantity is not None and self.quantity < 0:
            raise ValueError("COST_LEDGER_QUANTITY_INVALID")
        if self.confidence not in {"exact", "estimated", "unknown"}:
            raise ValueError("COST_LEDGER_CONFIDENCE_INVALID")
        if self.cost_basis not in {"provider_cost", "customer_charge"}:
            raise ValueError("COST_LEDGER_COST_BASIS_INVALID")


class CostLedgerGateway:
    """Compatibility gateway retained for NODE-20 callers.

    NODE-27's richer budget/reservation/usage runtime lives under ``lumi_api.costs``;
    both write the same append-only ``cost_ledger`` table.
    """

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    async def record_once(self, entry: CostLedgerEntry) -> tuple[UUID, bool]:
        connection = await asyncpg.connect(self.dsn)
        try:
            async with connection.transaction():
                entry_id = new_uuid7()
                inserted = await connection.fetchrow(
                    """
                    INSERT INTO cost_ledger (
                        id, organization_id, operation_id, project_id, task_id,
                        agent_run_id, generation_id, provider_request_id,
                        reverses_entry_id, provider, model, entry_type, entry_key, amount,
                        currency, quantity, unit, occurred_at, metadata_json, created_at,
                        pricing_snapshot_id, external_provider_request_id, confidence,
                        cost_basis, source
                    ) VALUES (
                        $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,
                        $19::jsonb,now(),$20,$21,$22,$23,$24
                    )
                    ON CONFLICT ON CONSTRAINT uq_cost_ledger_operation_entry_key DO NOTHING
                    RETURNING id
                    """,
                    entry_id,
                    entry.organization_id,
                    entry.operation_id,
                    entry.project_id,
                    entry.task_id,
                    entry.agent_run_id,
                    entry.generation_id,
                    entry.provider_request_id,
                    entry.reverses_entry_id,
                    entry.provider,
                    entry.model,
                    entry.entry_type,
                    entry.entry_key,
                    entry.amount,
                    entry.currency,
                    entry.quantity,
                    entry.unit,
                    entry.occurred_at,
                    json.dumps(entry.metadata_json, ensure_ascii=False, separators=(",", ":")),
                    entry.pricing_snapshot_id,
                    entry.external_provider_request_id,
                    entry.confidence,
                    entry.cost_basis,
                    entry.source,
                )
                if inserted is not None:
                    return inserted["id"], True
                existing = await connection.fetchrow(
                    """
                    SELECT id, organization_id, amount, currency, provider, model,
                           pricing_snapshot_id, external_provider_request_id, confidence,
                           cost_basis
                    FROM cost_ledger
                    WHERE operation_id = $1 AND entry_type = $2 AND entry_key = $3
                    FOR SHARE
                    """,
                    entry.operation_id,
                    entry.entry_type,
                    entry.entry_key,
                )
                if existing is None:
                    raise RuntimeError("COST_LEDGER_CONFLICT_ROW_DISAPPEARED")
                if (
                    existing["organization_id"] != entry.organization_id
                    or Decimal(existing["amount"]) != entry.amount
                    or existing["currency"] != entry.currency
                    or existing["provider"] != entry.provider
                    or existing["model"] != entry.model
                    or existing["pricing_snapshot_id"] != entry.pricing_snapshot_id
                    or existing["external_provider_request_id"]
                    != entry.external_provider_request_id
                    or existing["confidence"] != entry.confidence
                    or existing["cost_basis"] != entry.cost_basis
                ):
                    raise LedgerConflictError(
                        "same operation/entry_type/entry_key was reused with different ledger semantics"
                    )
                return existing["id"], False
        finally:
            await connection.close()
