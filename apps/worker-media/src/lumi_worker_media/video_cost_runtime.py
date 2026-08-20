from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import asyncpg

from .video_generation_ports import PostgresVideoCostObserver


class ScopedPostgresVideoCostObserver(PostgresVideoCostObserver):
    """Reconcile NODE-48 provider cost inside the durable video-job tenant boundary.

    The paid child operation UUID is not treated as a tenant selector. The observer
    first resolves the one durable video_generation_jobs organization for the
    pipeline video_job_id, then requires both cost_ledger and idempotency_operations
    to belong to that same organization before accepting the canonical NODE-27 row.
    It never inserts or updates provider cost state.
    """

    async def record_terminal(
        self,
        *,
        video_job_id: str,
        shot_id: str,
        paid_operation_id: str,
        provider: str,
        model: str,
        provider_request_id: str | None,
        amount_usd: Decimal | None,
        confidence: str,
        pricing_snapshot_id: str | None,
    ) -> bool:
        del shot_id
        connection = await asyncpg.connect(self.dsn)
        try:
            scope_rows = await connection.fetch(
                """
                SELECT organization_id
                FROM video_generation_jobs
                WHERE job_snapshot ->> 'video_job_id' = $1
                ORDER BY created_at, id
                LIMIT 2
                """,
                video_job_id,
            )
            if len(scope_rows) != 1:
                raise RuntimeError("VIDEO_COST_JOB_SCOPE_NOT_UNIQUE")
            organization_id = scope_rows[0]["organization_id"]

            rows = await connection.fetch(
                """
                SELECT cl.amount, cl.confidence, cl.pricing_snapshot_id,
                       cl.external_provider_request_id
                FROM cost_ledger cl
                JOIN idempotency_operations io
                  ON io.id = cl.operation_id
                 AND io.organization_id = cl.organization_id
                WHERE cl.organization_id = $1
                  AND io.organization_id = $1
                  AND io.operation_type = 'paid_model_invocation'
                  AND io.business_scope_id = $2
                  AND cl.entry_type = 'actual_cost'
                  AND cl.cost_basis = 'provider_cost'
                  AND cl.provider = $3
                  AND cl.model = $4
                ORDER BY cl.occurred_at, cl.id
                LIMIT 2
                """,
                organization_id,
                UUID(paid_operation_id),
                provider,
                model,
            )
            if len(rows) != 1:
                raise RuntimeError("VIDEO_COST_LEDGER_ENTRY_NOT_UNIQUE")
            row = rows[0]
            if provider_request_id and row["external_provider_request_id"] != provider_request_id:
                raise RuntimeError("VIDEO_COST_PROVIDER_REQUEST_MISMATCH")
            if amount_usd is not None and Decimal(row["amount"]) != amount_usd:
                raise RuntimeError("VIDEO_COST_AMOUNT_MISMATCH")
            if str(row["confidence"]) != confidence.casefold():
                raise RuntimeError("VIDEO_COST_CONFIDENCE_MISMATCH")
            if pricing_snapshot_id is not None and row["pricing_snapshot_id"] != pricing_snapshot_id:
                raise RuntimeError("VIDEO_COST_PRICE_SNAPSHOT_MISMATCH")
            return True
        finally:
            await connection.close()


__all__ = ["ScopedPostgresVideoCostObserver"]
