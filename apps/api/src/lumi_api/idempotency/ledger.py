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

    def __post_init__(self) -> None:
        if not self.entry_type or len(self.entry_type) > 64:
            raise ValueError("COST_LEDGER_ENTRY_TYPE_INVALID")
        if len(self.currency) != 3 or self.currency != self.currency.upper():
            raise ValueError("COST_LEDGER_CURRENCY_INVALID")
        if self.occurred_at.tzinfo is None:
            raise ValueError("COST_LEDGER_OCCURRED_AT_TZ_REQUIRED")


class CostLedgerGateway:
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
                        reverses_entry_id, provider, model, entry_type, amount,
                        currency, quantity, unit, occurred_at, metadata_json, created_at
                    ) VALUES (
                        $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,
                        $18::jsonb,now()
                    )
                    ON CONFLICT ON CONSTRAINT uq_cost_ledger_operation_entry DO NOTHING
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
                    entry.amount,
                    entry.currency,
                    entry.quantity,
                    entry.unit,
                    entry.occurred_at,
                    json.dumps(entry.metadata_json, ensure_ascii=False, separators=(",", ":")),
                )
                if inserted is not None:
                    return inserted["id"], True
                existing = await connection.fetchrow(
                    """
                    SELECT id, organization_id, amount, currency, provider, model
                    FROM cost_ledger
                    WHERE operation_id = $1 AND entry_type = $2
                    FOR UPDATE
                    """,
                    entry.operation_id,
                    entry.entry_type,
                )
                if existing is None:
                    raise RuntimeError("COST_LEDGER_CONFLICT_ROW_DISAPPEARED")
                if (
                    existing["organization_id"] != entry.organization_id
                    or Decimal(existing["amount"]) != entry.amount
                    or existing["currency"] != entry.currency
                    or existing["provider"] != entry.provider
                    or existing["model"] != entry.model
                ):
                    raise LedgerConflictError(
                        "same operation/entry_type was reused with different ledger semantics"
                    )
                return existing["id"], False
        finally:
            await connection.close()
