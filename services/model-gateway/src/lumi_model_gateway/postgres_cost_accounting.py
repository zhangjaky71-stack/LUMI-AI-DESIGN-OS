from __future__ import annotations

import json
from collections.abc import Mapping
from decimal import Decimal
from typing import Protocol
from uuid import UUID, uuid4


class CostAccountingConnection(Protocol):
    """Minimal async PostgreSQL port used by the provider-cost accounting adapter."""

    async def fetchval(self, query: str, *args: object) -> object: ...


class CostAccountingDatabaseError(RuntimeError):
    """Normalized error surfaced to LedgerBudgetGuard without driver coupling."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class PostgresCostAccounting:
    """Durable NODE-27 accounting adapter backed by atomic PostgreSQL functions.

    The database owns the platform-wide UTC-day reservation lock and the canonical
    USD cap. ModelGateway therefore fails closed before any paid provider call if
    accounting is unavailable or the daily cap would be exceeded.
    """

    def __init__(self, connection: CostAccountingConnection) -> None:
        self.connection = connection

    async def reserve_provider_cost(
        self,
        *,
        organization_id: UUID,
        operation_id: UUID,
        project_id: UUID | None,
        task_id: UUID | None,
        agent_run_id: UUID | None,
        generation_id: UUID | None,
        provider: str,
        model: str,
        estimated_amount_usd: Decimal,
        confidence: str,
        pricing_snapshot_id: str | None,
        reservation_key: str,
    ) -> str:
        if estimated_amount_usd <= 0:
            raise CostAccountingDatabaseError(
                "COST_INVALID_ESTIMATE",
                "provider cost estimate must be positive",
            )
        proposed_ticket = uuid4()
        try:
            value = await self.connection.fetchval(
                """
                SELECT provider_cost_reserve(
                    $1::uuid, $2::uuid, $3::uuid, $4::uuid, $5::uuid, $6::uuid,
                    $7::text, $8::text, $9::numeric, $10::text, $11::text,
                    $12::text, $13::uuid
                )
                """,
                organization_id,
                operation_id,
                project_id,
                task_id,
                agent_run_id,
                generation_id,
                provider,
                model,
                estimated_amount_usd,
                confidence,
                pricing_snapshot_id,
                reservation_key,
                proposed_ticket,
            )
        except Exception as exc:  # pragma: no cover - driver-specific subclasses
            raise _normalize_db_error(exc) from exc
        if value is None:
            raise CostAccountingDatabaseError(
                "COST_GUARD_UNAVAILABLE",
                "provider cost reservation returned no ticket",
            )
        return str(value)

    async def commit_provider_cost(
        self,
        *,
        reservation_ticket: str,
        actual_amount_usd: Decimal,
        confidence: str,
        pricing_snapshot_id: str | None,
        provider_request_id: str | None,
        usage: dict[str, tuple[Decimal, str]],
    ) -> None:
        if actual_amount_usd < 0:
            raise CostAccountingDatabaseError(
                "COST_INVALID_ACTUAL",
                "provider actual cost cannot be negative",
            )
        usage_payload = {
            metric: {"quantity": str(quantity), "unit": unit}
            for metric, (quantity, unit) in sorted(usage.items())
        }
        try:
            await self.connection.fetchval(
                """
                SELECT provider_cost_commit(
                    $1::uuid, $2::numeric, $3::text, $4::text, $5::text,
                    $6::jsonb
                )
                """,
                UUID(reservation_ticket),
                actual_amount_usd,
                confidence,
                pricing_snapshot_id,
                provider_request_id,
                json.dumps(usage_payload, sort_keys=True, separators=(",", ":")),
            )
        except Exception as exc:  # pragma: no cover - driver-specific subclasses
            raise _normalize_db_error(exc) from exc

    async def release_provider_cost(
        self,
        *,
        reservation_ticket: str,
        reason: str,
    ) -> None:
        try:
            await self.connection.fetchval(
                "SELECT provider_cost_release($1::uuid, $2::text)",
                UUID(reservation_ticket),
                reason,
            )
        except Exception as exc:  # pragma: no cover - driver-specific subclasses
            raise _normalize_db_error(exc) from exc


_ERROR_MAP: Mapping[str, str] = {
    "COST_DAILY_CAP_EXCEEDED": "COST_QUOTA_EXCEEDED",
    "COST_GUARD_DISABLED": "COST_QUOTA_EXCEEDED",
    "COST_GUARD_POLICY_MISSING": "COST_QUOTA_EXCEEDED",
    "COST_GUARD_FAIL_CLOSED_REQUIRED": "COST_QUOTA_EXCEEDED",
    "COST_IDEMPOTENCY_COLLISION": "COST_ACCOUNTING_CONFLICT",
    "COST_RESERVATION_NOT_FOUND": "COST_ACCOUNTING_CONFLICT",
    "COST_RESERVATION_RELEASED": "COST_ACCOUNTING_CONFLICT",
}


def _normalize_db_error(exc: Exception) -> CostAccountingDatabaseError:
    text = str(exc)
    for marker, code in _ERROR_MAP.items():
        if marker in text:
            return CostAccountingDatabaseError(code, text)
    driver_code = getattr(exc, "code", None)
    if isinstance(driver_code, str) and driver_code.startswith("COST_"):
        normalized = _ERROR_MAP.get(driver_code, driver_code)
        return CostAccountingDatabaseError(normalized, text)
    return CostAccountingDatabaseError(
        "COST_GUARD_UNAVAILABLE",
        f"provider cost guard unavailable: {text}",
    )
