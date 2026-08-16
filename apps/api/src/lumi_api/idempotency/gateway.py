from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Awaitable, Callable, Protocol
from uuid import UUID

from .http_context import mark_replayed
from .models import (
    AcquireAction,
    AcquireResult,
    ErrorCategory,
    IdempotencyOperation,
    OperationRequest,
    OperationStatus,
    ProviderReconciliation,
    ProviderReconciliationStatus,
    SideEffectOutcome,
)


class IdempotencyConflict(RuntimeError):
    code = "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST"


class OperationInProgress(RuntimeError):
    code = "IDEMPOTENCY_OPERATION_IN_PROGRESS"


class IdempotencyFinalFailure(RuntimeError):
    code = "IDEMPOTENCY_OPERATION_FAILED_FINAL"


class AmbiguousSideEffect(RuntimeError):
    code = "AMBIGUOUS_SIDE_EFFECT"


class IdempotencyStore(Protocol):
    async def acquire(
        self,
        request: OperationRequest,
        *,
        lease_owner: str,
        now: datetime,
    ) -> AcquireResult: ...

    async def record_provider_request(
        self,
        organization_id: UUID,
        operation_id: UUID,
        *,
        provider_request_id: str,
        lease_owner: str,
        now: datetime,
    ) -> IdempotencyOperation: ...

    async def complete(
        self,
        organization_id: UUID,
        operation_id: UUID,
        *,
        lease_owner: str,
        outcome: SideEffectOutcome,
        now: datetime,
    ) -> IdempotencyOperation: ...

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
    ) -> IdempotencyOperation: ...

    async def mark_ambiguous(
        self,
        organization_id: UUID,
        operation_id: UUID,
        *,
        lease_owner: str,
        detail: str,
        now: datetime,
    ) -> IdempotencyOperation: ...


class IdempotencyMetrics(Protocol):
    def increment(self, metric: str) -> None: ...


class ProviderReconciler(Protocol):
    async def reconcile(
        self, operation: IdempotencyOperation
    ) -> ProviderReconciliation: ...


class NoopMetrics:
    def increment(self, metric: str) -> None:
        del metric


@dataclass(slots=True)
class SideEffectExecutionContext:
    store: IdempotencyStore
    organization_id: UUID
    operation_id: UUID
    lease_owner: str

    async def record_provider_request(
        self,
        provider_request_id: str,
        *,
        now: datetime | None = None,
    ) -> IdempotencyOperation:
        return await self.store.record_provider_request(
            self.organization_id,
            self.operation_id,
            provider_request_id=provider_request_id,
            lease_owner=self.lease_owner,
            now=now or datetime.now(UTC),
        )


SideEffectCallable = Callable[
    [SideEffectExecutionContext], SideEffectOutcome | Awaitable[SideEffectOutcome]
]


class SideEffectGateway:
    def __init__(
        self,
        store: IdempotencyStore,
        *,
        metrics: IdempotencyMetrics | None = None,
    ) -> None:
        self.store = store
        self.metrics = metrics or NoopMetrics()

    async def execute(
        self,
        request: OperationRequest,
        effect: SideEffectCallable,
        *,
        lease_owner: str,
        reconciler: ProviderReconciler | None = None,
        now: datetime | None = None,
    ) -> SideEffectOutcome:
        current_time = now or datetime.now(UTC)
        acquired = await self.store.acquire(request, lease_owner=lease_owner, now=current_time)
        if acquired.action is AcquireAction.CONFLICT:
            self.metrics.increment("idempotency_conflict_total")
            raise IdempotencyConflict(IdempotencyConflict.code)
        if acquired.action is AcquireAction.REPLAY:
            self.metrics.increment("idempotency_replay_total")
            self.metrics.increment("duplicate_prevented_total")
            mark_replayed()
            return self._replay(acquired.operation)
        if acquired.action is AcquireAction.WAIT:
            self.metrics.increment("duplicate_prevented_total")
            raise OperationInProgress(OperationInProgress.code)
        if acquired.action is AcquireAction.FINAL_FAILURE:
            self.metrics.increment("duplicate_prevented_total")
            if acquired.operation.error_category is ErrorCategory.AMBIGUOUS:
                raise AmbiguousSideEffect(
                    acquired.operation.error_message or AmbiguousSideEffect.code
                )
            raise IdempotencyFinalFailure(
                acquired.operation.error_code or IdempotencyFinalFailure.code
            )
        if acquired.action is AcquireAction.RECOVER:
            self.metrics.increment("stale_lease_total")
            recovered = await self._reconcile_or_recover(
                request,
                acquired.operation,
                reconciler=reconciler,
                lease_owner=lease_owner,
                now=current_time,
            )
            if recovered is not None:
                mark_replayed()
                return recovered
        if acquired.action not in {AcquireAction.EXECUTE, AcquireAction.RECOVER}:
            raise RuntimeError(f"unsupported acquire action: {acquired.action}")

        context = SideEffectExecutionContext(
            store=self.store,
            organization_id=request.organization_id,
            operation_id=acquired.operation.id,
            lease_owner=lease_owner,
        )
        try:
            value = effect(context)
            outcome = await value if inspect.isawaitable(value) else value
        except Exception as exc:
            retryable = bool(getattr(exc, "retryable", False))
            category = ErrorCategory.TRANSIENT if retryable else ErrorCategory.PERMANENT
            await self.store.fail(
                request.organization_id,
                acquired.operation.id,
                lease_owner=lease_owner,
                category=category,
                code=str(getattr(exc, "code", type(exc).__name__))[:128],
                message=str(exc)[:2000],
                retryable=retryable,
                now=current_time,
            )
            raise
        operation = await self.store.complete(
            request.organization_id,
            acquired.operation.id,
            lease_owner=lease_owner,
            outcome=outcome,
            now=current_time,
        )
        return outcome.model_copy(update={"operation_id": operation.id, "replayed": False})

    async def _reconcile_or_recover(
        self,
        request: OperationRequest,
        operation: IdempotencyOperation,
        *,
        reconciler: ProviderReconciler | None,
        lease_owner: str,
        now: datetime,
    ) -> SideEffectOutcome | None:
        provider_may_have_accepted = bool(operation.provider_request_id)
        must_reconcile = request.paid or provider_may_have_accepted
        if not must_reconcile:
            return None
        if reconciler is None:
            detail = "provider reconciliation required before retrying ambiguous paid side effect"
            await self.store.mark_ambiguous(
                request.organization_id,
                operation.id,
                lease_owner=lease_owner,
                detail=detail,
                now=now,
            )
            self.metrics.increment("ambiguous_side_effect_total")
            raise AmbiguousSideEffect(detail)

        self.metrics.increment("provider_reconciliation_total")
        reconciliation = await reconciler.reconcile(operation)
        if reconciliation.status is ProviderReconciliationStatus.SUCCEEDED:
            outcome = SideEffectOutcome(
                result=reconciliation.result or {},
                result_ref=reconciliation.result_ref,
                response_status=reconciliation.response_status or 200,
                provider_request_id=(
                    reconciliation.provider_request_id or operation.provider_request_id
                ),
            )
            completed = await self.store.complete(
                request.organization_id,
                operation.id,
                lease_owner=lease_owner,
                outcome=outcome,
                now=now,
            )
            self.metrics.increment("duplicate_prevented_total")
            return outcome.model_copy(update={"operation_id": completed.id, "replayed": True})
        if reconciliation.status is ProviderReconciliationStatus.RUNNING:
            raise OperationInProgress("provider side effect is still running")
        if reconciliation.status is ProviderReconciliationStatus.NOT_FOUND:
            if operation.provider_request_id:
                detail = "provider could not prove whether an accepted request executed"
                await self.store.mark_ambiguous(
                    request.organization_id,
                    operation.id,
                    lease_owner=lease_owner,
                    detail=detail,
                    now=now,
                )
                self.metrics.increment("ambiguous_side_effect_total")
                raise AmbiguousSideEffect(detail)
            return None

        detail = reconciliation.detail or "provider reconciliation returned ambiguous state"
        await self.store.mark_ambiguous(
            request.organization_id,
            operation.id,
            lease_owner=lease_owner,
            detail=detail,
            now=now,
        )
        self.metrics.increment("ambiguous_side_effect_total")
        raise AmbiguousSideEffect(detail)

    @staticmethod
    def _replay(operation: IdempotencyOperation) -> SideEffectOutcome:
        if operation.status is not OperationStatus.SUCCEEDED:
            raise RuntimeError("only succeeded operations may be replayed")
        return SideEffectOutcome(
            result=operation.response_json or {},
            result_ref=operation.result_ref,
            response_status=operation.response_status or 200,
            provider_request_id=operation.provider_request_id,
            replayed=True,
            operation_id=operation.id,
        )


def lease_expiry(now: datetime, seconds: int) -> datetime:
    return now + timedelta(seconds=seconds)
