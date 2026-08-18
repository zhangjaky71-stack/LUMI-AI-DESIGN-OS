from __future__ import annotations

import asyncio
import os
from collections.abc import Coroutine
from typing import Any, TypeVar
from uuid import uuid4

import asyncpg
import pytest

from lumi_api.idempotency.contracts import ClaimDecision, IdempotencyContext, OperationStatus
from lumi_api.idempotency.gateway import AmbiguousSideEffectError, SideEffectGateway
from lumi_api.persistence.seed import ORG_ID
from lumi_api.persistence.session import require_database_url

if os.environ.get("LUMI_DB_INTEGRATION") != "1":
    pytest.skip("set LUMI_DB_INTEGRATION=1 to run PostgreSQL tests", allow_module_level=True)

T = TypeVar("T")


def run(coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


def _asyncpg_dsn() -> str:
    return require_database_url().replace("postgresql+asyncpg://", "postgresql://", 1)


async def _delete_operation(operation_id: object) -> None:
    connection = await asyncpg.connect(_asyncpg_dsn())
    try:
        await connection.execute(
            "DELETE FROM idempotency_operations WHERE id = $1",
            operation_id,
        )
    finally:
        await connection.close()


async def _expire_lease(operation_id: object) -> None:
    connection = await asyncpg.connect(_asyncpg_dsn())
    try:
        await connection.execute(
            """
            UPDATE idempotency_operations
            SET lease_expires_at = now() - interval '1 second'
            WHERE id = $1
            """,
            operation_id,
        )
    finally:
        await connection.close()


async def _crash_after_provider_attempt_start_fails_closed() -> None:
    gateway = SideEffectGateway(_asyncpg_dsn())
    context = IdempotencyContext(
        organization_id=ORG_ID,
        operation_type="paid_model_invocation",
        idempotency_key=f"crash-barrier:{uuid4()}",
        request={"provider": "fixture", "model": "fixture-model", "prompt": "hello"},
        lease_seconds=5,
    )
    first = await gateway.claim(context, lease_owner="worker-before-crash")
    operation_id = first.snapshot.id
    try:
        assert first.decision == ClaimDecision.EXECUTE
        assert first.snapshot.attempt_count == 1

        await gateway.mark_provider_attempt_started(
            operation_id,
            lease_owner="worker-before-crash",
        )
        started = await gateway.get(operation_id)
        assert started.provider_attempt_started_at is not None
        assert started.provider_request_id is None

        # Simulate a process crash after the outbound provider attempt began
        # but before a provider request id could be durably recorded.
        await _expire_lease(operation_id)

        second = await gateway.claim(context, lease_owner="worker-after-crash")
        assert second.decision == ClaimDecision.AMBIGUOUS
        assert second.snapshot.status == OperationStatus.AMBIGUOUS
        assert second.snapshot.attempt_count == 1
        assert second.snapshot.provider_request_id is None
        assert second.snapshot.error_code == "PROVIDER_ATTEMPT_OUTCOME_UNKNOWN"
        assert "re-execution is forbidden" in (second.snapshot.ambiguity_reason or "")

        provider_calls = 0

        async def must_not_run(_handle: object) -> object:
            nonlocal provider_calls
            provider_calls += 1
            raise AssertionError("ambiguous paid side effect was executed twice")

        with pytest.raises(AmbiguousSideEffectError):
            await gateway.execute(
                context,
                lease_owner="worker-third-attempt",
                invoke=must_not_run,
            )
        assert provider_calls == 0
    finally:
        await _delete_operation(operation_id)


def test_crash_after_provider_attempt_start_fails_closed() -> None:
    run(_crash_after_provider_attempt_start_fails_closed())


async def _proven_not_accepted_failure_clears_barrier_for_safe_retry() -> None:
    gateway = SideEffectGateway(_asyncpg_dsn())
    context = IdempotencyContext(
        organization_id=ORG_ID,
        operation_type="paid_model_invocation",
        idempotency_key=f"safe-retry:{uuid4()}",
        request={"provider": "fixture", "model": "fixture-model", "prompt": "hello"},
        lease_seconds=5,
    )
    first = await gateway.claim(context, lease_owner="worker-not-accepted")
    operation_id = first.snapshot.id
    try:
        assert first.decision == ClaimDecision.EXECUTE
        await gateway.mark_provider_attempt_started(
            operation_id,
            lease_owner="worker-not-accepted",
        )
        await gateway.fail_retryable(
            operation_id,
            lease_owner="worker-not-accepted",
            error_code="PROVIDER_NOT_ACCEPTED",
        )

        retryable = await gateway.get(operation_id)
        assert retryable.status == OperationStatus.FAILED_RETRYABLE
        assert retryable.provider_attempt_started_at is None
        assert retryable.provider_request_id is None

        second = await gateway.claim(context, lease_owner="worker-safe-retry")
        assert second.decision == ClaimDecision.EXECUTE
        assert second.snapshot.attempt_count == 2
    finally:
        await _delete_operation(operation_id)


def test_proven_not_accepted_failure_clears_barrier_for_safe_retry() -> None:
    run(_proven_not_accepted_failure_clears_barrier_for_safe_retry())
