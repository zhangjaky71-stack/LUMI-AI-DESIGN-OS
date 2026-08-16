# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

import inspect
import json
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable
from uuid import UUID

from .gateway import (
    AmbiguousSideEffect,
    IdempotencyConflict,
    IdempotencyFinalFailure,
    OperationInProgress,
)
from .http_context import mark_replayed
from .models import (
    ErrorCategory,
    IdempotencyOperation,
    OperationRequest,
    OperationStatus,
    RecoveryState,
    SideEffectKind,
    SideEffectOutcome,
)
from .postgres import _asyncpg, _operation, _set_tenant

_DB_SIDE_EFFECTS = {
    SideEffectKind.GENERIC_WRITE,
    SideEffectKind.BILLING_CHARGE,
    SideEffectKind.BILLING_CREDIT,
}

DatabaseEffect = Callable[
    [Any, UUID],
    SideEffectOutcome | Awaitable[SideEffectOutcome],
]


class PostgresTransactionalSideEffectGateway:
    """Atomically couples an idempotency operation with one PostgreSQL mutation.

    The callback receives the already-open connection and must not commit or replace the
    transaction. External provider/object-store side effects are deliberately rejected.
    """

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    async def execute(
        self,
        request: OperationRequest,
        effect: DatabaseEffect,
        *,
        lease_owner: str,
        now: datetime,
    ) -> SideEffectOutcome:
        if request.paid and request.side_effect_kind is not SideEffectKind.BILLING_CHARGE:
            raise ValueError("PAID_EXTERNAL_EFFECT_REQUIRES_SIDE_EFFECT_GATEWAY")
        if request.side_effect_kind not in _DB_SIDE_EFFECTS:
            raise ValueError("EXTERNAL_EFFECT_NOT_ALLOWED_IN_DATABASE_GATEWAY")

        module = _asyncpg()
        connection = await module.connect(self.dsn)
        pending_error: Exception | None = None
        final_outcome: SideEffectOutcome | None = None
        operation_id: UUID | None = None
        try:
            async with connection.transaction():
                await _set_tenant(connection, request.organization_id)
                operation = await self._claim(
                    connection,
                    request,
                    lease_owner=lease_owner,
                    now=now,
                )
                if operation.status is OperationStatus.SUCCEEDED:
                    mark_replayed()
                    return SideEffectOutcome(
                        result=operation.response_json or {},
                        result_ref=operation.result_ref,
                        response_status=operation.response_status or 200,
                        provider_request_id=operation.provider_request_id,
                        replayed=True,
                        operation_id=operation.id,
                    )
                operation_id = operation.id
                try:
                    async with connection.transaction():
                        value = effect(connection, operation.id)
                        outcome = await value if inspect.isawaitable(value) else value
                except Exception as exc:
                    pending_error = exc
                    retryable = bool(getattr(exc, "retryable", False))
                    await self._record_failure(
                        connection,
                        operation,
                        lease_owner=lease_owner,
                        exc=exc,
                        retryable=retryable,
                        now=now,
                    )
                else:
                    await self._record_success(
                        connection,
                        operation,
                        lease_owner=lease_owner,
                        outcome=outcome,
                        now=now,
                    )
                    final_outcome = outcome.model_copy(
                        update={"operation_id": operation.id, "replayed": False}
                    )
        finally:
            await connection.close()

        if pending_error is not None:
            raise pending_error
        if final_outcome is None or operation_id is None:
            raise RuntimeError("IDEMPOTENCY_DATABASE_OUTCOME_MISSING")
        return final_outcome

    async def _claim(
        self,
        connection: Any,
        request: OperationRequest,
        *,
        lease_owner: str,
        now: datetime,
    ) -> IdempotencyOperation:
        from lumi_api.domain.ids import new_uuid7

        row = await connection.fetchrow(
            """
            INSERT INTO idempotency_operations(
              id,organization_id,idempotency_key,operation_type,request_hash,
              business_scope_id,side_effect_kind,compensation_mode,paid,
              status,recovery_state,lease_owner,lease_expires_at,expires_at,
              created_at,updated_at,version
            ) VALUES(
              $1,$2,$3,$4,$5,$6,$7,$8,$9,
              'in_progress','none',$10,$11,$12,$13,$13,1
            )
            ON CONFLICT (organization_id,operation_type,idempotency_key) DO NOTHING
            RETURNING *
            """,
            new_uuid7(),
            request.organization_id,
            request.idempotency_key,
            request.operation_type,
            request.request_hash,
            request.business_scope_id,
            request.side_effect_kind.value,
            request.compensation_mode.value,
            request.paid,
            lease_owner,
            now + timedelta(seconds=request.lease_seconds),
            now + timedelta(seconds=request.ttl_seconds),
            now,
        )
        if row is not None:
            return _operation(row)

        row = await connection.fetchrow(
            """
            SELECT * FROM idempotency_operations
            WHERE organization_id=$1 AND operation_type=$2 AND idempotency_key=$3
            FOR UPDATE
            """,
            request.organization_id,
            request.operation_type,
            request.idempotency_key,
        )
        if row is None:
            raise RuntimeError("IDEMPOTENCY_CONFLICT_ROW_NOT_VISIBLE")
        current = _operation(row)
        if current.request_hash != request.request_hash:
            raise IdempotencyConflict(IdempotencyConflict.code)
        if current.recovery_state is RecoveryState.AMBIGUOUS:
            raise AmbiguousSideEffect(
                current.error_message or AmbiguousSideEffect.code
            )
        if current.status is OperationStatus.SUCCEEDED:
            return current
        if current.status is OperationStatus.FAILED_FINAL:
            raise IdempotencyFinalFailure(
                current.error_code or IdempotencyFinalFailure.code
            )
        if (
            current.status is OperationStatus.IN_PROGRESS
            and current.lease_expires_at is not None
            and current.lease_expires_at > now
        ):
            raise OperationInProgress(OperationInProgress.code)
        if current.status not in {
            OperationStatus.NEW,
            OperationStatus.IN_PROGRESS,
            OperationStatus.FAILED_RETRYABLE,
        }:
            raise IdempotencyFinalFailure(IdempotencyFinalFailure.code)

        row = await connection.fetchrow(
            """
            UPDATE idempotency_operations
            SET status='in_progress',recovery_state='none',lease_owner=$3,
                lease_expires_at=$4,updated_at=$5,version=version+1
            WHERE id=$1 AND organization_id=$2
            RETURNING *
            """,
            current.id,
            request.organization_id,
            lease_owner,
            now + timedelta(seconds=request.lease_seconds),
            now,
        )
        if row is None:
            raise RuntimeError("IDEMPOTENCY_RECOVERY_CLAIM_LOST")
        return _operation(row)

    @staticmethod
    async def _record_success(
        connection: Any,
        operation: IdempotencyOperation,
        *,
        lease_owner: str,
        outcome: SideEffectOutcome,
        now: datetime,
    ) -> None:
        result = await connection.execute(
            """
            UPDATE idempotency_operations
            SET status='succeeded',recovery_state='none',result_ref=$4,
                response_status=$5,response_json=$6::jsonb,
                lease_owner=NULL,lease_expires_at=NULL,
                error_category=NULL,error_code=NULL,error_message=NULL,
                completed_at=$7,updated_at=$7,version=version+1
            WHERE id=$1 AND organization_id=$2 AND lease_owner=$3
              AND status='in_progress'
            """,
            operation.id,
            operation.organization_id,
            lease_owner,
            outcome.result_ref,
            outcome.response_status,
            json.dumps(outcome.result, separators=(",", ":")),
            now,
        )
        if not result.endswith(" 1"):
            raise ValueError("IDEMPOTENCY_LEASE_NOT_OWNED")

    @staticmethod
    async def _record_failure(
        connection: Any,
        operation: IdempotencyOperation,
        *,
        lease_owner: str,
        exc: Exception,
        retryable: bool,
        now: datetime,
    ) -> None:
        category = ErrorCategory.TRANSIENT if retryable else ErrorCategory.PERMANENT
        status = "failed_retryable" if retryable else "failed_final"
        completed_at = None if retryable else now
        result = await connection.execute(
            """
            UPDATE idempotency_operations
            SET status=$4,recovery_state='none',error_category=$5,
                error_code=$6,error_message=$7,lease_owner=NULL,
                lease_expires_at=NULL,completed_at=$8,updated_at=$9,
                version=version+1
            WHERE id=$1 AND organization_id=$2 AND lease_owner=$3
              AND status='in_progress'
            """,
            operation.id,
            operation.organization_id,
            lease_owner,
            status,
            category.value,
            str(getattr(exc, "code", type(exc).__name__))[:128],
            str(exc)[:2000],
            completed_at,
            now,
        )
        if not result.endswith(" 1"):
            raise ValueError("IDEMPOTENCY_LEASE_NOT_OWNED")
