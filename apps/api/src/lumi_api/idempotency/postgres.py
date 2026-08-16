# pyright: reportMissingImports=false, reportMissingModuleSource=false
from __future__ import annotations

import importlib
import json
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from lumi_api.domain.ids import new_uuid7

from .models import (
    AcquireAction,
    AcquireResult,
    CompensationMode,
    ErrorCategory,
    IdempotencyOperation,
    OperationRequest,
    OperationStatus,
    RecoveryState,
    SideEffectKind,
    SideEffectOutcome,
)


def _asyncpg() -> Any:
    try:
        return importlib.import_module("asyncpg")
    except ModuleNotFoundError as exc:
        raise RuntimeError("asyncpg is required for PostgreSQL idempotency storage") from exc


async def _set_tenant(connection: Any, organization_id: UUID) -> None:
    await connection.execute(
        "SELECT set_config('app.current_organization_id', $1, true)",
        str(organization_id),
    )


def _json_object(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("IDEMPOTENCY_JSON_OBJECT_REQUIRED")


def _operation(row: Any) -> IdempotencyOperation:
    return IdempotencyOperation(
        id=row["id"],
        organization_id=row["organization_id"],
        idempotency_key=row["idempotency_key"],
        operation_type=row["operation_type"],
        request_hash=row["request_hash"],
        business_scope_id=row["business_scope_id"],
        side_effect_kind=SideEffectKind(row["side_effect_kind"]),
        compensation_mode=CompensationMode(row["compensation_mode"]),
        paid=bool(row["paid"]),
        status=OperationStatus(row["status"]),
        recovery_state=RecoveryState(row["recovery_state"]),
        lease_owner=row["lease_owner"],
        lease_expires_at=row["lease_expires_at"],
        provider_request_id=row["provider_request_id"],
        result_ref=row["result_ref"],
        response_status=row["response_status"],
        response_json=_json_object(row["response_json"]),
        error_category=(ErrorCategory(row["error_category"]) if row["error_category"] else None),
        error_code=row["error_code"],
        error_message=row["error_message"],
        recovery_detail=_json_object(row["recovery_detail"]) or {},
        expires_at=row["expires_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        completed_at=row["completed_at"],
        version=int(row["version"]),
    )


class PostgresIdempotencyStore:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    async def acquire(
        self,
        request: OperationRequest,
        *,
        lease_owner: str,
        now: datetime,
    ) -> AcquireResult:
        module = _asyncpg()
        connection = await module.connect(self.dsn)
        try:
            async with connection.transaction():
                await _set_tenant(connection, request.organization_id)
                row = await connection.fetchrow(
                    """
                    INSERT INTO idempotency_operations(
                      id, organization_id, idempotency_key, operation_type, request_hash,
                      business_scope_id, side_effect_kind, compensation_mode, paid,
                      status, recovery_state, lease_owner, lease_expires_at, expires_at,
                      created_at, updated_at, version
                    ) VALUES(
                      $1,$2,$3,$4,$5,$6,$7,$8,$9,
                      'in_progress','none',$10,$11,$12,$13,$13,1
                    )
                    ON CONFLICT (organization_id, operation_type, idempotency_key) DO NOTHING
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
                    return AcquireResult(action=AcquireAction.EXECUTE, operation=_operation(row))

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
                    return AcquireResult(action=AcquireAction.CONFLICT, operation=current)
                if current.recovery_state is RecoveryState.AMBIGUOUS:
                    return AcquireResult(action=AcquireAction.FINAL_FAILURE, operation=current)
                if current.status is OperationStatus.SUCCEEDED:
                    return AcquireResult(action=AcquireAction.REPLAY, operation=current)
                if current.status is OperationStatus.FAILED_FINAL:
                    return AcquireResult(action=AcquireAction.FINAL_FAILURE, operation=current)
                if (
                    current.status is OperationStatus.IN_PROGRESS
                    and current.lease_expires_at is not None
                    and current.lease_expires_at > now
                ):
                    return AcquireResult(action=AcquireAction.WAIT, operation=current)
                if current.status not in {
                    OperationStatus.NEW,
                    OperationStatus.IN_PROGRESS,
                    OperationStatus.FAILED_RETRYABLE,
                }:
                    return AcquireResult(action=AcquireAction.FINAL_FAILURE, operation=current)
                recovery_state = (
                    RecoveryState.RECONCILING
                    if request.paid or current.provider_request_id
                    else RecoveryState.NONE
                )
                row = await connection.fetchrow(
                    """
                    UPDATE idempotency_operations
                    SET status='in_progress', recovery_state=$4, lease_owner=$5,
                        lease_expires_at=$6, updated_at=$7, version=version+1
                    WHERE id=$1 AND organization_id=$2 AND request_hash=$3
                    RETURNING *
                    """,
                    current.id,
                    request.organization_id,
                    request.request_hash,
                    recovery_state.value,
                    lease_owner,
                    now + timedelta(seconds=request.lease_seconds),
                    now,
                )
                if row is None:
                    raise RuntimeError("IDEMPOTENCY_RECOVERY_CLAIM_LOST")
                return AcquireResult(action=AcquireAction.RECOVER, operation=_operation(row))
        finally:
            await connection.close()

    async def record_provider_request(
        self,
        organization_id: UUID,
        operation_id: UUID,
        *,
        provider_request_id: str,
        lease_owner: str,
        now: datetime,
    ) -> IdempotencyOperation:
        return await self._owned_update(
            organization_id,
            operation_id,
            lease_owner=lease_owner,
            sql="""
            UPDATE idempotency_operations
            SET provider_request_id=COALESCE(provider_request_id,$4),
                updated_at=$5, version=version+1
            WHERE id=$1 AND organization_id=$2 AND status='in_progress'
              AND lease_owner=$3
              AND (provider_request_id IS NULL OR provider_request_id=$4)
            RETURNING *
            """,
            args=(provider_request_id, now),
        )

    async def complete(
        self,
        organization_id: UUID,
        operation_id: UUID,
        *,
        lease_owner: str,
        outcome: SideEffectOutcome,
        now: datetime,
    ) -> IdempotencyOperation:
        module = _asyncpg()
        connection = await module.connect(self.dsn)
        try:
            async with connection.transaction():
                await _set_tenant(connection, organization_id)
                row = await connection.fetchrow(
                    """
                    UPDATE idempotency_operations
                    SET status='succeeded', recovery_state='none',
                        provider_request_id=COALESCE(provider_request_id,$4),
                        result_ref=$5, response_status=$6, response_json=$7::jsonb,
                        error_category=NULL,error_code=NULL,error_message=NULL,
                        lease_owner=NULL,lease_expires_at=NULL,
                        completed_at=$8,updated_at=$8,version=version+1
                    WHERE id=$1 AND organization_id=$2 AND status='in_progress'
                      AND lease_owner=$3
                      AND (provider_request_id IS NULL OR $4 IS NULL OR provider_request_id=$4)
                    RETURNING *
                    """,
                    operation_id,
                    organization_id,
                    lease_owner,
                    outcome.provider_request_id,
                    outcome.result_ref,
                    outcome.response_status,
                    json.dumps(outcome.result, separators=(",", ":")),
                    now,
                )
                if row is None:
                    raise ValueError("IDEMPOTENCY_LEASE_NOT_OWNED")
                return _operation(row)
        finally:
            await connection.close()

    async def fail(
        self,
        organization_id: UUID,
        operation_id: UUID,
        *,
        lease_owner: str,
        category: ErrorCategory,
        code: str,
        message: str,
        retryable: bool,
        now: datetime,
    ) -> IdempotencyOperation:
        module = _asyncpg()
        connection = await module.connect(self.dsn)
        status = "failed_retryable" if retryable else "failed_final"
        try:
            async with connection.transaction():
                await _set_tenant(connection, organization_id)
                row = await connection.fetchrow(
                    """
                    UPDATE idempotency_operations
                    SET status=$4,recovery_state='none',error_category=$5,
                        error_code=$6,error_message=$7,lease_owner=NULL,
                        lease_expires_at=NULL,completed_at=$8,updated_at=$8,
                        version=version+1
                    WHERE id=$1 AND organization_id=$2 AND status='in_progress'
                      AND lease_owner=$3
                    RETURNING *
                    """,
                    operation_id,
                    organization_id,
                    lease_owner,
                    status,
                    category.value,
                    code[:128],
                    message[:2000],
                    now if not retryable else None,
                )
                if row is None:
                    raise ValueError("IDEMPOTENCY_LEASE_NOT_OWNED")
                return _operation(row)
        finally:
            await connection.close()

    async def mark_ambiguous(
        self,
        organization_id: UUID,
        operation_id: UUID,
        *,
        lease_owner: str,
        detail: str,
        now: datetime,
    ) -> IdempotencyOperation:
        module = _asyncpg()
        connection = await module.connect(self.dsn)
        try:
            async with connection.transaction():
                await _set_tenant(connection, organization_id)
                row = await connection.fetchrow(
                    """
                    UPDATE idempotency_operations
                    SET status='failed_retryable',recovery_state='ambiguous',
                        error_category='ambiguous',error_code='AMBIGUOUS_SIDE_EFFECT',
                        error_message=$4,recovery_detail=$5::jsonb,
                        lease_owner=NULL,lease_expires_at=NULL,
                        updated_at=$6,version=version+1
                    WHERE id=$1 AND organization_id=$2 AND status='in_progress'
                      AND lease_owner=$3
                    RETURNING *
                    """,
                    operation_id,
                    organization_id,
                    lease_owner,
                    detail[:2000],
                    '{"requires_operator_review":true}',
                    now,
                )
                if row is None:
                    raise ValueError("IDEMPOTENCY_LEASE_NOT_OWNED")
                return _operation(row)
        finally:
            await connection.close()

    async def _owned_update(
        self,
        organization_id: UUID,
        operation_id: UUID,
        *,
        lease_owner: str,
        sql: str,
        args: tuple[Any, ...],
    ) -> IdempotencyOperation:
        module = _asyncpg()
        connection = await module.connect(self.dsn)
        try:
            async with connection.transaction():
                await _set_tenant(connection, organization_id)
                row = await connection.fetchrow(
                    sql,
                    operation_id,
                    organization_id,
                    lease_owner,
                    *args,
                )
                if row is None:
                    raise ValueError("IDEMPOTENCY_LEASE_NOT_OWNED")
                return _operation(row)
        finally:
            await connection.close()
