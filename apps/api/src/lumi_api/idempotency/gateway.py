from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

import asyncpg
from lumi_domain import new_uuid7

from .contracts import (
    ClaimDecision,
    IdempotencyContext,
    OperationStatus,
    ProviderReconciliation,
    ProviderState,
    SideEffectResult,
)


class MetricsSink(Protocol):
    def increment(self, metric: str, value: int = 1) -> None: ...


class _NoopMetrics:
    def increment(self, metric: str, value: int = 1) -> None:
        del metric, value


class ProviderReconciler(Protocol):
    async def lookup(self, provider_request_id: str) -> ProviderReconciliation: ...


class IdempotencyError(RuntimeError):
    code = "IDEMPOTENCY_ERROR"
    http_status = 409


class IdempotencyConflictError(IdempotencyError):
    code = "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST"


class IdempotencyInProgressError(IdempotencyError):
    code = "IDEMPOTENCY_OPERATION_IN_PROGRESS"
    http_status = 425


class LeaseLostError(IdempotencyError):
    code = "IDEMPOTENCY_LEASE_LOST"


class AmbiguousSideEffectError(IdempotencyError):
    code = "AMBIGUOUS_SIDE_EFFECT"
    http_status = 503


class PriorOperationFailedError(IdempotencyError):
    code = "IDEMPOTENCY_PRIOR_FINAL_FAILURE"


class SideEffectExecutionError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class RetryableSideEffectError(SideEffectExecutionError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, retryable=True)


@dataclass(frozen=True, slots=True)
class OperationSnapshot:
    id: UUID
    organization_id: UUID
    operation_type: str
    idempotency_key: str
    request_hash: str
    status: OperationStatus
    lease_owner: str | None
    lease_expires_at: datetime | None
    provider_request_id: str | None
    result_ref: str | None
    result_json: dict[str, Any]
    response_status: int | None
    error_code: str | None
    error_category: str | None
    completed_at: datetime | None
    attempt_count: int
    ambiguity_reason: str | None


@dataclass(frozen=True, slots=True)
class OperationClaim:
    decision: ClaimDecision
    snapshot: OperationSnapshot


@dataclass(frozen=True, slots=True)
class GatewayResponse:
    operation_id: UUID
    replayed: bool
    result_ref: str | None
    result_json: dict[str, Any]
    response_status: int


class OperationHandle:
    def __init__(
        self,
        gateway: SideEffectGateway,
        snapshot: OperationSnapshot,
        *,
        lease_owner: str,
    ) -> None:
        self._gateway = gateway
        self.snapshot = snapshot
        self.lease_owner = lease_owner
        self.provider_request_recorded = snapshot.provider_request_id is not None

    @property
    def provider_idempotency_key(self) -> str:
        return self.snapshot.idempotency_key

    async def record_provider_request(self, provider_request_id: str) -> None:
        await self._gateway.record_provider_request(
            self.snapshot.id,
            lease_owner=self.lease_owner,
            provider_request_id=provider_request_id,
        )
        self.provider_request_recorded = True


class SideEffectGateway:
    def __init__(self, dsn: str, *, metrics: MetricsSink | None = None) -> None:
        self.dsn = dsn
        self.metrics = metrics or _NoopMetrics()

    async def claim(self, context: IdempotencyContext, *, lease_owner: str) -> OperationClaim:
        if not lease_owner or len(lease_owner) > 200:
            raise ValueError("IDEMPOTENCY_LEASE_OWNER_INVALID")
        now = datetime.now(UTC)
        lease_expires_at = now + timedelta(seconds=context.lease_seconds)
        connection = await asyncpg.connect(self.dsn)
        try:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    INSERT INTO idempotency_operations (
                        id, organization_id, idempotency_key, operation_type,
                        business_scope_id, status, request_hash, lease_owner,
                        lease_expires_at, attempt_count, result_json,
                        created_at, updated_at, version
                    ) VALUES (
                        $1,$2,$3,$4,$5,'in_progress',$6,$7,$8,1,'{}'::jsonb,
                        now(),now(),1
                    )
                    ON CONFLICT (organization_id, operation_type, idempotency_key)
                    DO NOTHING
                    RETURNING *
                    """,
                    new_uuid7(),
                    context.organization_id,
                    context.idempotency_key,
                    context.operation_type,
                    context.business_scope_id,
                    context.request_hash,
                    lease_owner,
                    lease_expires_at,
                )
                if row is not None:
                    return OperationClaim(ClaimDecision.EXECUTE, _snapshot(row))

                row = await connection.fetchrow(
                    """
                    SELECT * FROM idempotency_operations
                    WHERE organization_id = $1
                      AND operation_type = $2
                      AND idempotency_key = $3
                    FOR UPDATE
                    """,
                    context.organization_id,
                    context.operation_type,
                    context.idempotency_key,
                )
                if row is None:
                    raise RuntimeError("IDEMPOTENCY_OPERATION_DISAPPEARED")
                current = _snapshot(row)
                if current.request_hash != context.request_hash:
                    self.metrics.increment("idempotency_conflict_total")
                    raise IdempotencyConflictError(
                        "same idempotency key was reused with a different request"
                    )
                if current.status == OperationStatus.SUCCEEDED:
                    self.metrics.increment("idempotency_replay_total")
                    self.metrics.increment("duplicate_prevented_total")
                    return OperationClaim(ClaimDecision.REPLAY, current)
                if current.status == OperationStatus.FAILED_FINAL:
                    self.metrics.increment("duplicate_prevented_total")
                    return OperationClaim(ClaimDecision.FINAL_FAILURE, current)
                if current.status == OperationStatus.AMBIGUOUS:
                    self.metrics.increment("duplicate_prevented_total")
                    return OperationClaim(ClaimDecision.AMBIGUOUS, current)
                if (
                    current.status == OperationStatus.IN_PROGRESS
                    and current.lease_expires_at is not None
                    and current.lease_expires_at > now
                ):
                    self.metrics.increment("duplicate_prevented_total")
                    return OperationClaim(ClaimDecision.WAIT, current)

                if current.lease_expires_at is not None and current.lease_expires_at <= now:
                    self.metrics.increment("stale_lease_total")
                decision = (
                    ClaimDecision.RECONCILE
                    if current.provider_request_id
                    else ClaimDecision.EXECUTE
                )
                row = await connection.fetchrow(
                    """
                    UPDATE idempotency_operations
                    SET status = 'in_progress', lease_owner = $2, lease_expires_at = $3,
                        attempt_count = attempt_count + 1, updated_at = now(),
                        version = version + 1
                    WHERE id = $1
                    RETURNING *
                    """,
                    current.id,
                    lease_owner,
                    lease_expires_at,
                )
                if row is None:
                    raise RuntimeError("IDEMPOTENCY_OPERATION_DISAPPEARED")
                if decision == ClaimDecision.RECONCILE:
                    self.metrics.increment("duplicate_prevented_total")
                return OperationClaim(decision, _snapshot(row))
        finally:
            await connection.close()

    async def record_provider_request(
        self,
        operation_id: UUID,
        *,
        lease_owner: str,
        provider_request_id: str,
    ) -> None:
        if not provider_request_id or len(provider_request_id) > 512:
            raise ValueError("PROVIDER_REQUEST_ID_INVALID")
        connection = await asyncpg.connect(self.dsn)
        try:
            row = await connection.fetchrow(
                """
                UPDATE idempotency_operations
                SET provider_request_id = COALESCE(provider_request_id, $3),
                    updated_at = now(), version = version + 1
                WHERE id = $1 AND lease_owner = $2 AND status = 'in_progress'
                  AND (provider_request_id IS NULL OR provider_request_id = $3)
                RETURNING id
                """,
                operation_id,
                lease_owner,
                provider_request_id,
            )
            if row is None:
                raise LeaseLostError("provider request could not be bound to the active lease")
        finally:
            await connection.close()

    async def succeed(
        self,
        operation_id: UUID,
        *,
        lease_owner: str,
        result: SideEffectResult,
    ) -> None:
        if not 100 <= result.response_status <= 599:
            raise ValueError("IDEMPOTENCY_RESPONSE_STATUS_INVALID")
        connection = await asyncpg.connect(self.dsn)
        try:
            row = await connection.fetchrow(
                """
                UPDATE idempotency_operations
                SET status = 'succeeded', result_ref = $3, result_json = $4::jsonb,
                    response_status = $5, error_code = NULL, error_category = NULL,
                    ambiguity_reason = NULL, completed_at = now(), lease_owner = NULL,
                    lease_expires_at = NULL, updated_at = now(), version = version + 1
                WHERE id = $1 AND lease_owner = $2 AND status = 'in_progress'
                RETURNING id
                """,
                operation_id,
                lease_owner,
                result.result_ref,
                _json(result.result_json),
                result.response_status,
            )
            if row is None:
                raise LeaseLostError("success could not be committed because the lease was lost")
        finally:
            await connection.close()

    async def fail_retryable(
        self,
        operation_id: UUID,
        *,
        lease_owner: str,
        error_code: str,
    ) -> None:
        await self._fail(
            operation_id,
            lease_owner=lease_owner,
            status=OperationStatus.FAILED_RETRYABLE,
            error_category="transient",
            error_code=error_code,
        )

    async def fail_final(
        self,
        operation_id: UUID,
        *,
        lease_owner: str,
        error_code: str,
    ) -> None:
        await self._fail(
            operation_id,
            lease_owner=lease_owner,
            status=OperationStatus.FAILED_FINAL,
            error_category="permanent",
            error_code=error_code,
        )

    async def fail_needs_reconciliation(
        self,
        operation_id: UUID,
        *,
        lease_owner: str,
        error_code: str,
    ) -> None:
        await self._fail(
            operation_id,
            lease_owner=lease_owner,
            status=OperationStatus.FAILED_RETRYABLE,
            error_category="ambiguous",
            error_code=error_code,
        )

    async def mark_ambiguous(
        self,
        operation_id: UUID,
        *,
        lease_owner: str,
        reason: str,
    ) -> None:
        self.metrics.increment("ambiguous_side_effect_total")
        connection = await asyncpg.connect(self.dsn)
        try:
            row = await connection.fetchrow(
                """
                UPDATE idempotency_operations
                SET status = 'ambiguous', error_category = 'ambiguous',
                    error_code = 'AMBIGUOUS_SIDE_EFFECT', ambiguity_reason = $3,
                    completed_at = now(), lease_owner = NULL, lease_expires_at = NULL,
                    updated_at = now(), version = version + 1
                WHERE id = $1 AND lease_owner = $2 AND status = 'in_progress'
                RETURNING id
                """,
                operation_id,
                lease_owner,
                reason[:2000],
            )
            if row is None:
                raise LeaseLostError("ambiguity state could not be committed because lease was lost")
        finally:
            await connection.close()

    async def reconcile(
        self,
        claim: OperationClaim,
        *,
        reconciler: ProviderReconciler,
    ) -> OperationClaim:
        if claim.decision != ClaimDecision.RECONCILE:
            raise ValueError("IDEMPOTENCY_RECONCILE_CLAIM_REQUIRED")
        provider_request_id = claim.snapshot.provider_request_id
        lease_owner = claim.snapshot.lease_owner
        if not provider_request_id or not lease_owner:
            raise ValueError("IDEMPOTENCY_RECONCILE_STATE_INVALID")
        self.metrics.increment("provider_reconciliation_total")
        outcome = await reconciler.lookup(provider_request_id)
        if outcome.state == ProviderState.SUCCEEDED:
            await self.succeed(
                claim.snapshot.id,
                lease_owner=lease_owner,
                result=SideEffectResult(
                    result_ref=outcome.result_ref,
                    result_json=outcome.result_json,
                    response_status=outcome.response_status or 200,
                ),
            )
            self.metrics.increment("duplicate_prevented_total")
            return OperationClaim(ClaimDecision.REPLAY, await self.get(claim.snapshot.id))
        if outcome.state == ProviderState.PENDING:
            await self._extend_lease(claim.snapshot.id, lease_owner=lease_owner)
            return OperationClaim(ClaimDecision.WAIT, await self.get(claim.snapshot.id))
        if outcome.state == ProviderState.FAILED:
            await self._confirmed_provider_failure(claim.snapshot.id, lease_owner=lease_owner)
            return OperationClaim(ClaimDecision.RETRY_SAFE, await self.get(claim.snapshot.id))
        await self.mark_ambiguous(
            claim.snapshot.id,
            lease_owner=lease_owner,
            reason=outcome.detail or "provider state could not be reconciled",
        )
        return OperationClaim(ClaimDecision.AMBIGUOUS, await self.get(claim.snapshot.id))

    async def execute(
        self,
        context: IdempotencyContext,
        *,
        lease_owner: str,
        invoke: Any,
        reconciler: ProviderReconciler | None = None,
    ) -> GatewayResponse:
        claim = await self.claim(context, lease_owner=lease_owner)
        if claim.decision == ClaimDecision.RECONCILE:
            if reconciler is None:
                await self.mark_ambiguous(
                    claim.snapshot.id,
                    lease_owner=lease_owner,
                    reason="provider request exists but no reconciler is configured",
                )
                raise AmbiguousSideEffectError("provider reconciliation is required")
            claim = await self.reconcile(claim, reconciler=reconciler)
            if claim.decision == ClaimDecision.RETRY_SAFE:
                claim = await self.claim(context, lease_owner=lease_owner)
        if claim.decision == ClaimDecision.REPLAY:
            return _response(claim.snapshot, replayed=True)
        if claim.decision == ClaimDecision.WAIT:
            raise IdempotencyInProgressError("an equivalent operation already owns the lease")
        if claim.decision == ClaimDecision.FINAL_FAILURE:
            raise PriorOperationFailedError(claim.snapshot.error_code or "prior operation failed")
        if claim.decision == ClaimDecision.AMBIGUOUS:
            raise AmbiguousSideEffectError(
                claim.snapshot.ambiguity_reason or "side effect outcome is ambiguous"
            )
        if claim.decision != ClaimDecision.EXECUTE:
            raise RuntimeError(f"unexpected idempotency decision: {claim.decision}")

        handle = OperationHandle(self, claim.snapshot, lease_owner=lease_owner)
        try:
            result = await invoke(handle)
            if not isinstance(result, SideEffectResult):
                raise TypeError("SIDE_EFFECT_RESULT_REQUIRED")
        except RetryableSideEffectError as exc:
            await self.fail_retryable(
                claim.snapshot.id,
                lease_owner=lease_owner,
                error_code=exc.code,
            )
            raise
        except SideEffectExecutionError as exc:
            if exc.retryable:
                await self.fail_retryable(
                    claim.snapshot.id,
                    lease_owner=lease_owner,
                    error_code=exc.code,
                )
            else:
                await self.fail_final(
                    claim.snapshot.id,
                    lease_owner=lease_owner,
                    error_code=exc.code,
                )
            raise
        except Exception as exc:
            if handle.provider_request_recorded:
                await self.fail_needs_reconciliation(
                    claim.snapshot.id,
                    lease_owner=lease_owner,
                    error_code=type(exc).__name__,
                )
                raise
            await self.mark_ambiguous(
                claim.snapshot.id,
                lease_owner=lease_owner,
                reason=(
                    "execution failed before a provider request could be durably bound; "
                    f"manual/provider-native idempotency reconciliation required: {exc}"
                ),
            )
            raise AmbiguousSideEffectError(str(exc)) from exc

        await self.succeed(claim.snapshot.id, lease_owner=lease_owner, result=result)
        return GatewayResponse(
            operation_id=claim.snapshot.id,
            replayed=False,
            result_ref=result.result_ref,
            result_json=result.result_json,
            response_status=result.response_status,
        )

    async def get(self, operation_id: UUID) -> OperationSnapshot:
        connection = await asyncpg.connect(self.dsn)
        try:
            row = await connection.fetchrow(
                "SELECT * FROM idempotency_operations WHERE id = $1",
                operation_id,
            )
            if row is None:
                raise KeyError("IDEMPOTENCY_OPERATION_NOT_FOUND")
            return _snapshot(row)
        finally:
            await connection.close()

    async def _fail(
        self,
        operation_id: UUID,
        *,
        lease_owner: str,
        status: OperationStatus,
        error_category: str,
        error_code: str,
    ) -> None:
        connection = await asyncpg.connect(self.dsn)
        try:
            row = await connection.fetchrow(
                """
                UPDATE idempotency_operations
                SET status = $3, error_category = $4, error_code = $5,
                    completed_at = CASE WHEN $3 = 'failed_final' THEN now() ELSE NULL END,
                    lease_owner = NULL, lease_expires_at = NULL,
                    updated_at = now(), version = version + 1
                WHERE id = $1 AND lease_owner = $2 AND status = 'in_progress'
                RETURNING id
                """,
                operation_id,
                lease_owner,
                status.value,
                error_category,
                error_code[:64],
            )
            if row is None:
                raise LeaseLostError("failure state could not be committed because lease was lost")
        finally:
            await connection.close()

    async def _extend_lease(self, operation_id: UUID, *, lease_owner: str) -> None:
        connection = await asyncpg.connect(self.dsn)
        try:
            row = await connection.fetchrow(
                """
                UPDATE idempotency_operations
                SET lease_expires_at = now() + interval '60 seconds',
                    updated_at = now(), version = version + 1
                WHERE id = $1 AND lease_owner = $2 AND status = 'in_progress'
                RETURNING id
                """,
                operation_id,
                lease_owner,
            )
            if row is None:
                raise LeaseLostError("reconciliation lease was lost")
        finally:
            await connection.close()

    async def _confirmed_provider_failure(self, operation_id: UUID, *, lease_owner: str) -> None:
        connection = await asyncpg.connect(self.dsn)
        try:
            row = await connection.fetchrow(
                """
                UPDATE idempotency_operations
                SET status = 'failed_retryable', provider_request_id = NULL,
                    error_category = 'transient', error_code = 'PROVIDER_CONFIRMED_FAILED',
                    lease_owner = NULL, lease_expires_at = NULL,
                    updated_at = now(), version = version + 1
                WHERE id = $1 AND lease_owner = $2 AND status = 'in_progress'
                RETURNING id
                """,
                operation_id,
                lease_owner,
            )
            if row is None:
                raise LeaseLostError("provider failure could not be committed because lease was lost")
        finally:
            await connection.close()


def _snapshot(row: asyncpg.Record) -> OperationSnapshot:
    return OperationSnapshot(
        id=row["id"],
        organization_id=row["organization_id"],
        operation_type=row["operation_type"],
        idempotency_key=row["idempotency_key"],
        request_hash=row["request_hash"],
        status=OperationStatus(row["status"]),
        lease_owner=row["lease_owner"],
        lease_expires_at=row["lease_expires_at"],
        provider_request_id=row["provider_request_id"],
        result_ref=row["result_ref"],
        result_json=dict(row["result_json"] or {}),
        response_status=row["response_status"],
        error_code=row["error_code"],
        error_category=row["error_category"],
        completed_at=row["completed_at"],
        attempt_count=int(row["attempt_count"]),
        ambiguity_reason=row["ambiguity_reason"],
    )


def _response(snapshot: OperationSnapshot, *, replayed: bool) -> GatewayResponse:
    return GatewayResponse(
        operation_id=snapshot.id,
        replayed=replayed,
        result_ref=snapshot.result_ref,
        result_json=snapshot.result_json,
        response_status=snapshot.response_status or 200,
    )


def _json(value: dict[str, Any]) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
