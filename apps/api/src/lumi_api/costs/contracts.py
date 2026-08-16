from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any
from uuid import UUID


class CostEntryType(StrEnum):
    ACTUAL_COST = "actual_cost"
    RESERVATION = "reservation"
    RESERVATION_RELEASE = "reservation_release"
    ADJUSTMENT = "adjustment"
    REVERSAL = "reversal"


class CostConfidence(StrEnum):
    EXACT = "exact"
    ESTIMATED = "estimated"
    UNKNOWN = "unknown"


class CostBasis(StrEnum):
    PROVIDER_COST = "provider_cost"
    CUSTOMER_CHARGE = "customer_charge"


class BudgetScope(StrEnum):
    ORGANIZATION = "organization"
    PROJECT = "project"
    AGENT_RUN = "agent_run"
    TASK = "task"
    OPERATION = "operation"


class ReservationStatus(StrEnum):
    ACTIVE = "active"
    COMMITTED = "committed"
    RELEASED = "released"
    EXPIRED = "expired"


class QuotaMetric(StrEnum):
    PROVIDER_COST_USD = "provider_cost_usd"
    IMAGE_GENERATIONS = "image_generations"
    VIDEO_SECONDS = "video_seconds"
    CONCURRENT_GENERATIONS = "concurrent_generations"
    ASSET_STORAGE_BYTES = "asset_storage_bytes"


class BudgetExceeded(RuntimeError):
    code = "COST_BUDGET_EXCEEDED"


class QuotaExceeded(RuntimeError):
    code = "COST_QUOTA_EXCEEDED"


class CostLedgerConflict(RuntimeError):
    code = "COST_LEDGER_OPERATION_REUSED_WITH_DIFFERENT_ENTRY"


class ReservationConflict(RuntimeError):
    code = "COST_RESERVATION_CONFLICT"


@dataclass(frozen=True, slots=True)
class CostContext:
    organization_id: UUID
    operation_id: UUID
    project_id: UUID | None = None
    task_id: UUID | None = None
    agent_run_id: UUID | None = None
    generation_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class UsageFact:
    metric: str
    quantity: Decimal
    unit: str
    entry_key: str = "primary"

    def __post_init__(self) -> None:
        _require_decimal(self.quantity, "USAGE_QUANTITY_INVALID")
        if not self.metric or len(self.metric) > 100:
            raise ValueError("USAGE_METRIC_INVALID")
        if not self.unit or len(self.unit) > 64:
            raise ValueError("USAGE_UNIT_INVALID")
        if self.quantity < 0:
            raise ValueError("USAGE_QUANTITY_INVALID")
        if not self.entry_key or len(self.entry_key) > 128:
            raise ValueError("USAGE_ENTRY_KEY_INVALID")


@dataclass(frozen=True, slots=True)
class ActualCost:
    context: CostContext
    provider: str
    model: str
    amount: Decimal
    currency: str = "USD"
    confidence: CostConfidence = CostConfidence.UNKNOWN
    pricing_snapshot_id: str | None = None
    external_provider_request_id: str | None = None
    entry_key: str = "primary"
    usage: tuple[UsageFact, ...] = ()
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_decimal(self.amount, "COST_AMOUNT_INVALID")
        if not self.provider or len(self.provider) > 100:
            raise ValueError("COST_PROVIDER_INVALID")
        if not self.model or len(self.model) > 255:
            raise ValueError("COST_MODEL_INVALID")
        if self.amount < 0:
            raise ValueError("COST_AMOUNT_INVALID")
        _validate_currency(self.currency)
        if self.pricing_snapshot_id is not None and len(self.pricing_snapshot_id) > 128:
            raise ValueError("COST_PRICING_SNAPSHOT_INVALID")
        if self.external_provider_request_id is not None and len(
            self.external_provider_request_id
        ) > 512:
            raise ValueError("COST_PROVIDER_REQUEST_ID_INVALID")
        if not self.entry_key or len(self.entry_key) > 128:
            raise ValueError("COST_ENTRY_KEY_INVALID")
        if self.occurred_at.tzinfo is None:
            raise ValueError("COST_OCCURRED_AT_TZ_REQUIRED")
        _validate_metadata(self.metadata)


@dataclass(frozen=True, slots=True)
class BudgetReservationRequest:
    context: CostContext
    provider: str
    model: str
    estimated_amount: Decimal
    currency: str = "USD"
    pricing_snapshot_id: str | None = None
    confidence: CostConfidence = CostConfidence.ESTIMATED
    reservation_key: str | None = None
    ttl_seconds: int = 900
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_decimal(self.estimated_amount, "COST_RESERVATION_AMOUNT_INVALID")
        if not self.provider or len(self.provider) > 100:
            raise ValueError("COST_PROVIDER_INVALID")
        if not self.model or len(self.model) > 255:
            raise ValueError("COST_MODEL_INVALID")
        if self.estimated_amount < 0:
            raise ValueError("COST_RESERVATION_AMOUNT_INVALID")
        _validate_currency(self.currency)
        if not 5 <= self.ttl_seconds <= 86_400:
            raise ValueError("COST_RESERVATION_TTL_INVALID")
        key = self.reservation_key or f"{self.provider}:{self.model}"
        if not key or len(key) > 512:
            raise ValueError("COST_RESERVATION_KEY_INVALID")
        _validate_metadata(self.metadata)

    @property
    def key(self) -> str:
        return self.reservation_key or f"{self.provider}:{self.model}"


@dataclass(frozen=True, slots=True)
class ReservationHandle:
    reservation_id: UUID
    request: BudgetReservationRequest
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class LedgerWriteResult:
    entry_id: UUID
    inserted: bool


@dataclass(frozen=True, slots=True)
class CostAdjustment:
    context: CostContext
    target_entry_id: UUID
    amount_delta: Decimal
    reason: str
    entry_key: str
    confidence: CostConfidence = CostConfidence.EXACT
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_decimal(self.amount_delta, "COST_ADJUSTMENT_AMOUNT_INVALID")
        if not self.reason or len(self.reason) > 1000:
            raise ValueError("COST_ADJUSTMENT_REASON_INVALID")
        if not self.entry_key or len(self.entry_key) > 128:
            raise ValueError("COST_ENTRY_KEY_INVALID")
        if self.occurred_at.tzinfo is None:
            raise ValueError("COST_OCCURRED_AT_TZ_REQUIRED")
        _validate_metadata(self.metadata)


@dataclass(frozen=True, slots=True)
class CostSummary:
    organization_id: UUID
    currency: str
    actual_cost: Decimal
    adjustments: Decimal
    reversals: Decimal
    net_provider_cost: Decimal
    active_reservations: Decimal
    unknown_cost_entries: int
    from_time: datetime
    to_time: datetime
    project_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class UsageSummary:
    organization_id: UUID
    metric: str
    quantity: Decimal
    unit: str
    from_time: datetime
    to_time: datetime
    project_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class QuotaLease:
    lease_id: UUID
    organization_id: UUID
    operation_id: UUID
    metric: str
    quantity: Decimal
    unit: str
    expires_at: datetime
    replayed: bool = False


def decimal_amount(value: Decimal | str | int) -> Decimal:
    if isinstance(value, float):
        raise ValueError("COST_FLOAT_FORBIDDEN")
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("COST_DECIMAL_INVALID") from exc
    if not result.is_finite():
        raise ValueError("COST_DECIMAL_NON_FINITE")
    return result


def month_period_key(at: datetime) -> str:
    if at.tzinfo is None:
        raise ValueError("COST_PERIOD_TZ_REQUIRED")
    utc = at.astimezone(UTC)
    return f"month:{utc.year:04d}-{utc.month:02d}"


def lifetime_period_key() -> str:
    return "lifetime"


def _require_decimal(value: object, code: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(code)


def _validate_currency(currency: str) -> None:
    if len(currency) != 3 or not currency.isascii() or not currency.isupper():
        raise ValueError("COST_CURRENCY_INVALID")


def _validate_metadata(metadata: dict[str, Any]) -> None:
    if len(metadata) > 64:
        raise ValueError("COST_METADATA_TOO_LARGE")
    for key, value in metadata.items():
        if not isinstance(key, str) or not key or len(key) > 128:
            raise ValueError("COST_METADATA_KEY_INVALID")
        if isinstance(value, float):
            raise ValueError("COST_METADATA_FLOAT_FORBIDDEN")
        if isinstance(value, (bytes, bytearray, memoryview)):
            raise ValueError("COST_METADATA_BINARY_FORBIDDEN")
