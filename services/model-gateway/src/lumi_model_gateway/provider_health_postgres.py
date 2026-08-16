from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import uuid4

from .provider_health import (
    ProviderHealthAuditEvent,
    ProviderHealthSnapshot,
)


class AsyncHealthConnection(Protocol):
    async def execute(
        self,
        query: str,
        *args: object,
    ) -> object: ...


class PostgresProviderHealthPersistence:
    """Dependency-free asyncpg-compatible append-only persistence boundary."""

    async def append_summary(
        self,
        connection: AsyncHealthConnection,
        snapshot: ProviderHealthSnapshot,
        *,
        source_instance: str | None = None,
    ) -> str:
        summary_id = str(uuid4())
        await connection.execute(
            """
            INSERT INTO provider_health_summaries (
              id,
              provider,
              model,
              capability,
              state,
              score,
              sample_count,
              success_rate,
              failure_rate,
              rate_limit_rate,
              timeout_rate,
              latency_p50_ms,
              latency_p95_ms,
              queue_completion_p95_ms,
              consecutive_failures,
              observed_at,
              source_instance
            ) VALUES (
              $1::uuid,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,
              $12,$13,$14,$15,$16,$17
            )
            """,
            summary_id,
            snapshot.provider,
            snapshot.model,
            snapshot.capability,
            snapshot.state.value,
            snapshot.score,
            snapshot.sample_count,
            _rate(snapshot.success_rate),
            _rate(snapshot.failure_rate),
            _rate(snapshot.rate_limit_rate),
            _rate(snapshot.timeout_rate),
            snapshot.latency_p50_ms,
            snapshot.latency_p95_ms,
            snapshot.queue_completion_p95_ms,
            snapshot.consecutive_failures,
            _epoch_datetime(snapshot.updated_at_epoch),
            source_instance,
        )
        return summary_id

    async def append_audit(
        self,
        connection: AsyncHealthConnection,
        event: ProviderHealthAuditEvent,
    ) -> str:
        audit_id = str(uuid4())
        await connection.execute(
            """
            INSERT INTO provider_health_override_audit (
              id,
              action,
              provider,
              model,
              capability,
              actor_id,
              reason,
              observed_at,
              expires_at
            ) VALUES (
              $1::uuid,$2,$3,$4,$5,$6,$7,$8,$9
            )
            """,
            audit_id,
            event.action,
            event.provider,
            event.model,
            event.capability,
            event.actor_id,
            event.reason,
            _epoch_datetime(event.observed_at_epoch),
            (
                None
                if event.expires_at_epoch is None
                else _epoch_datetime(event.expires_at_epoch)
            ),
        )
        return audit_id


def _rate(value: float) -> Decimal:
    if not 0 <= value <= 1:
        raise ValueError("PROVIDER_HEALTH_PERSIST_RATE_INVALID")
    return Decimal(str(value)).quantize(Decimal("0.000001"))


def _epoch_datetime(value: float) -> datetime:
    if value < 0:
        raise ValueError("PROVIDER_HEALTH_PERSIST_TIME_INVALID")
    return datetime.fromtimestamp(value, tz=UTC)


def summary_payload(snapshot: ProviderHealthSnapshot) -> dict[str, Any]:
    """Stable, secret-free summary shape for metrics/export tooling."""

    return {
        "provider": snapshot.provider,
        "model": snapshot.model,
        "capability": snapshot.capability,
        "state": snapshot.state.value,
        "score": snapshot.score,
        "sample_count": snapshot.sample_count,
        "success_rate": snapshot.success_rate,
        "failure_rate": snapshot.failure_rate,
        "rate_limit_rate": snapshot.rate_limit_rate,
        "timeout_rate": snapshot.timeout_rate,
        "latency_p50_ms": snapshot.latency_p50_ms,
        "latency_p95_ms": snapshot.latency_p95_ms,
        "queue_completion_p95_ms": snapshot.queue_completion_p95_ms,
        "consecutive_failures": snapshot.consecutive_failures,
        "observed_at_epoch": snapshot.updated_at_epoch,
        "reason": snapshot.reason,
    }
