from __future__ import annotations

import asyncio
from datetime import datetime
from uuid import UUID

from .gateway import lease_expiry
from .models import (
    AcquireAction,
    AcquireResult,
    ErrorCategory,
    IdempotencyOperation,
    OperationRequest,
    OperationStatus,
    RecoveryState,
    SideEffectOutcome,
)


class MemoryMetrics:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}

    def increment(self, metric: str) -> None:
        self.values[metric] = self.values.get(metric, 0) + 1


class MemoryIdempotencyStore:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self.records: dict[tuple[UUID, str, str], IdempotencyOperation] = {}
        self.by_id: dict[UUID, tuple[UUID, str, str]] = {}

    @staticmethod
    def _key(request: OperationRequest) -> tuple[UUID, str, str]:
        return (request.organization_id, request.operation_type, request.idempotency_key)

    async def acquire(
        self,
        request: OperationRequest,
        *,
        lease_owner: str,
        now: datetime,
    ) -> AcquireResult:
        async with self._lock:
            key = self._key(request)
            record = self.records.get(key)
            if record is None:
                record = IdempotencyOperation(
                    organization_id=request.organization_id,
                    idempotency_key=request.idempotency_key,
                    operation_type=request.operation_type,
                    request_hash=request.request_hash,
                    business_scope_id=request.business_scope_id,
                    side_effect_kind=request.side_effect_kind,
                    compensation_mode=request.compensation_mode,
                    paid=request.paid,
                    status=OperationStatus.IN_PROGRESS,
                    lease_owner=lease_owner,
                    lease_expires_at=lease_expiry(now, request.lease_seconds),
                    created_at=now,
                    updated_at=now,
                )
                self.records[key] = record
                self.by_id[record.id] = key
                return AcquireResult(action=AcquireAction.EXECUTE, operation=record)

            if record.request_hash != request.request_hash:
                return AcquireResult(action=AcquireAction.CONFLICT, operation=record)
            if record.recovery_state is RecoveryState.AMBIGUOUS:
                return AcquireResult(action=AcquireAction.FINAL_FAILURE, operation=record)
            if record.status is OperationStatus.SUCCEEDED:
                return AcquireResult(action=AcquireAction.REPLAY, operation=record)
            if record.status is OperationStatus.FAILED_FINAL:
                return AcquireResult(action=AcquireAction.FINAL_FAILURE, operation=record)
            if (
                record.status is OperationStatus.IN_PROGRESS
                and record.lease_expires_at is not None
                and record.lease_expires_at > now
            ):
                return AcquireResult(action=AcquireAction.WAIT, operation=record)

            recoverable = record.status in {
                OperationStatus.NEW,
                OperationStatus.IN_PROGRESS,
                OperationStatus.FAILED_RETRYABLE,
            }
            if not recoverable:
                return AcquireResult(action=AcquireAction.FINAL_FAILURE, operation=record)
            claimed = record.model_copy(
                update={
                    "status": OperationStatus.IN_PROGRESS,
                    "recovery_state": (
                        RecoveryState.RECONCILING
                        if request.paid or record.provider_request_id
                        else RecoveryState.NONE
                    ),
                    "lease_owner": lease_owner,
                    "lease_expires_at": lease_expiry(now, request.lease_seconds),
                    "updated_at": now,
                    "version": record.version + 1,
                }
            )
            self.records[key] = claimed
            return AcquireResult(action=AcquireAction.RECOVER, operation=claimed)

    async def record_provider_request(
        self,
        operation_id: UUID,
        *,
        provider_request_id: str,
        lease_owner: str,
        now: datetime,
    ) -> IdempotencyOperation:
        async with self._lock:
            record, key = self._owned(operation_id, lease_owner)
            if record.provider_request_id not in {None, provider_request_id}:
                raise ValueError("PROVIDER_REQUEST_ID_IMMUTABLE")
            updated = record.model_copy(
                update={
                    "provider_request_id": provider_request_id,
                    "updated_at": now,
                    "version": record.version + 1,
                }
            )
            self.records[key] = updated
            return updated

    async def complete(
        self,
        operation_id: UUID,
        *,
        lease_owner: str,
        outcome: SideEffectOutcome,
        now: datetime,
    ) -> IdempotencyOperation:
        async with self._lock:
            record, key = self._owned(operation_id, lease_owner)
            provider_request_id = outcome.provider_request_id or record.provider_request_id
            if (
                record.provider_request_id is not None
                and provider_request_id != record.provider_request_id
            ):
                raise ValueError("PROVIDER_REQUEST_ID_IMMUTABLE")
            updated = record.model_copy(
                update={
                    "status": OperationStatus.SUCCEEDED,
                    "recovery_state": RecoveryState.NONE,
                    "provider_request_id": provider_request_id,
                    "result_ref": outcome.result_ref,
                    "response_status": outcome.response_status,
                    "response_json": dict(outcome.result),
                    "error_category": None,
                    "error_code": None,
                    "error_message": None,
                    "lease_owner": None,
                    "lease_expires_at": None,
                    "updated_at": now,
                    "completed_at": now,
                    "version": record.version + 1,
                }
            )
            self.records[key] = updated
            return updated

    async def fail(
        self,
        operation_id: UUID,
        *,
        lease_owner: str,
        category: ErrorCategory,
        code: str,
        message: str,
        retryable: bool,
        now: datetime,
    ) -> IdempotencyOperation:
        async with self._lock:
            record, key = self._owned(operation_id, lease_owner)
            status = (
                OperationStatus.FAILED_RETRYABLE if retryable else OperationStatus.FAILED_FINAL
            )
            updated = record.model_copy(
                update={
                    "status": status,
                    "recovery_state": RecoveryState.NONE,
                    "error_category": category,
                    "error_code": code[:128],
                    "error_message": message[:2000],
                    "lease_owner": None,
                    "lease_expires_at": None,
                    "updated_at": now,
                    "completed_at": now if status is OperationStatus.FAILED_FINAL else None,
                    "version": record.version + 1,
                }
            )
            self.records[key] = updated
            return updated

    async def mark_ambiguous(
        self,
        operation_id: UUID,
        *,
        lease_owner: str,
        detail: str,
        now: datetime,
    ) -> IdempotencyOperation:
        async with self._lock:
            record, key = self._owned(operation_id, lease_owner)
            updated = record.model_copy(
                update={
                    "status": OperationStatus.FAILED_RETRYABLE,
                    "recovery_state": RecoveryState.AMBIGUOUS,
                    "error_category": ErrorCategory.AMBIGUOUS,
                    "error_code": "AMBIGUOUS_SIDE_EFFECT",
                    "error_message": detail[:2000],
                    "recovery_detail": {"requires_operator_review": True},
                    "lease_owner": None,
                    "lease_expires_at": None,
                    "updated_at": now,
                    "version": record.version + 1,
                }
            )
            self.records[key] = updated
            return updated

    def _owned(
        self, operation_id: UUID, lease_owner: str
    ) -> tuple[IdempotencyOperation, tuple[UUID, str, str]]:
        key = self.by_id.get(operation_id)
        if key is None:
            raise ValueError("IDEMPOTENCY_OPERATION_NOT_FOUND")
        record = self.records[key]
        if record.status is not OperationStatus.IN_PROGRESS:
            raise ValueError("IDEMPOTENCY_OPERATION_NOT_IN_PROGRESS")
        if record.lease_owner != lease_owner:
            raise ValueError("IDEMPOTENCY_LEASE_NOT_OWNED")
        return record, key
