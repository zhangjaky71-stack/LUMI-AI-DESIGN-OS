from __future__ import annotations

import asyncio
import os
from collections.abc import Coroutine
from decimal import Decimal
from typing import Any, TypeVar
from uuid import UUID, uuid4

import asyncpg
import pytest
from lumi_model_gateway import (
    Capability,
    CostConfidence,
    CostEstimate,
    DeliveryState,
    ErrorCategory,
    ModelOutput,
    ModelRequest,
    ModelResult,
    ProviderInvocationError,
    ResultStatus,
    Timing,
    Usage,
)

from lumi_api.model_paid_guard import PostgresModelPaidInvocationGuard
from lumi_api.persistence.seed import ORG_ID
from lumi_api.persistence.session import require_database_url

if os.environ.get("LUMI_DB_INTEGRATION") != "1":
    pytest.skip("set LUMI_DB_INTEGRATION=1 to run PostgreSQL tests", allow_module_level=True)

T = TypeVar("T")
_PROVIDER = "fixture-provider"
_MODEL = "fixture-model"


def run(coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


def _asyncpg_dsn() -> str:
    return require_database_url().replace("postgresql+asyncpg://", "postgresql://", 1)


def _request(operation_id: UUID | None = None, *, prompt: str = "hello") -> ModelRequest:
    return ModelRequest(
        organization_id=ORG_ID,
        operation_id=operation_id or uuid4(),
        capability=Capability.LLM_REASONING,
        inputs={"prompt": prompt},
    )


def _result(*, provider_request_id: str = "provider-request-1") -> ModelResult:
    return ModelResult(
        status=ResultStatus.SUCCEEDED,
        provider=_PROVIDER,
        model=_MODEL,
        provider_request_id=provider_request_id,
        outputs=(ModelOutput(kind="text", value="done", mime_type="text/plain"),),
        usage=Usage(input_tokens=5, output_tokens=2, total_tokens=7),
        timing=Timing(total_ms=100, ttft_ms=25, queue_ms=5),
        cost=CostEstimate(
            amount_usd=Decimal("0.01000000"),
            confidence=CostConfidence.EXACT,
            price_snapshot_id="fixture-pricing-v1",
        ),
        safety_metadata={"fixture": True},
        finish_reason="stop",
    )


async def _cleanup(operation_id: UUID) -> None:
    connection = await asyncpg.connect(_asyncpg_dsn())
    try:
        await connection.execute(
            """
            DELETE FROM idempotency_operations
            WHERE business_scope_id = $1
              AND operation_type = 'paid_model_invocation'
            """,
            operation_id,
        )
    finally:
        await connection.close()


async def _successful_invocation_replays_without_second_provider_call() -> None:
    request = _request()
    guard = PostgresModelPaidInvocationGuard(_asyncpg_dsn())
    provider_calls = 0

    async def invoke() -> ModelResult:
        nonlocal provider_calls
        provider_calls += 1
        return _result()

    try:
        first = await guard.execute(
            request=request,
            provider=_PROVIDER,
            model=_MODEL,
            invoke=invoke,
        )
        second = await guard.execute(
            request=request,
            provider=_PROVIDER,
            model=_MODEL,
            invoke=invoke,
        )
        assert first == second == _result()
        assert provider_calls == 1

        connection = await asyncpg.connect(_asyncpg_dsn())
        try:
            row = await connection.fetchrow(
                """
                SELECT status, attempt_count, provider_attempt_started_at, provider_request_id
                FROM idempotency_operations
                WHERE business_scope_id = $1
                  AND operation_type = 'paid_model_invocation'
                """,
                request.operation_id,
            )
        finally:
            await connection.close()
        assert row is not None
        assert row["status"] == "succeeded"
        assert int(row["attempt_count"]) == 1
        assert row["provider_attempt_started_at"] is not None
        assert row["provider_request_id"] == "provider-request-1"
    finally:
        await _cleanup(request.operation_id)


def test_successful_invocation_replays_without_second_provider_call() -> None:
    run(_successful_invocation_replays_without_second_provider_call())


async def _not_accepted_preserves_safe_retry_semantics() -> None:
    request = _request()
    guard = PostgresModelPaidInvocationGuard(_asyncpg_dsn())
    provider_calls = 0

    async def invoke() -> ModelResult:
        nonlocal provider_calls
        provider_calls += 1
        if provider_calls == 1:
            raise ProviderInvocationError(
                ErrorCategory.RATE_LIMIT,
                "fixture rate limit before acceptance",
                provider=_PROVIDER,
                model=_MODEL,
                delivery_state=DeliveryState.NOT_ACCEPTED,
            )
        return _result(provider_request_id="provider-request-retry")

    try:
        with pytest.raises(ProviderInvocationError) as first_error:
            await guard.execute(
                request=request,
                provider=_PROVIDER,
                model=_MODEL,
                invoke=invoke,
            )
        assert first_error.value.delivery_state == DeliveryState.NOT_ACCEPTED

        retry = await guard.execute(
            request=request,
            provider=_PROVIDER,
            model=_MODEL,
            invoke=invoke,
        )
        assert retry.provider_request_id == "provider-request-retry"
        assert provider_calls == 2

        connection = await asyncpg.connect(_asyncpg_dsn())
        try:
            row = await connection.fetchrow(
                """
                SELECT status, attempt_count, provider_attempt_started_at, provider_request_id
                FROM idempotency_operations
                WHERE business_scope_id = $1
                  AND operation_type = 'paid_model_invocation'
                """,
                request.operation_id,
            )
        finally:
            await connection.close()
        assert row is not None
        assert row["status"] == "succeeded"
        assert int(row["attempt_count"]) == 2
        assert row["provider_attempt_started_at"] is not None
        assert row["provider_request_id"] == "provider-request-retry"
    finally:
        await _cleanup(request.operation_id)


def test_not_accepted_preserves_safe_retry_semantics() -> None:
    run(_not_accepted_preserves_safe_retry_semantics())


async def _unknown_delivery_is_persistently_fail_closed() -> None:
    request = _request()
    guard = PostgresModelPaidInvocationGuard(_asyncpg_dsn())
    provider_calls = 0

    async def ambiguous_invoke() -> ModelResult:
        nonlocal provider_calls
        provider_calls += 1
        raise ProviderInvocationError(
            ErrorCategory.TIMEOUT,
            "fixture timeout after request may have been accepted",
            provider=_PROVIDER,
            model=_MODEL,
            delivery_state=DeliveryState.UNKNOWN,
        )

    async def must_not_run() -> ModelResult:
        nonlocal provider_calls
        provider_calls += 1
        raise AssertionError("ambiguous paid model invocation was executed twice")

    try:
        with pytest.raises(ProviderInvocationError) as first_error:
            await guard.execute(
                request=request,
                provider=_PROVIDER,
                model=_MODEL,
                invoke=ambiguous_invoke,
            )
        assert first_error.value.delivery_state == DeliveryState.UNKNOWN
        assert provider_calls == 1

        with pytest.raises(ProviderInvocationError) as second_error:
            await guard.execute(
                request=request,
                provider=_PROVIDER,
                model=_MODEL,
                invoke=must_not_run,
            )
        assert second_error.value.delivery_state == DeliveryState.UNKNOWN
        assert provider_calls == 1

        connection = await asyncpg.connect(_asyncpg_dsn())
        try:
            row = await connection.fetchrow(
                """
                SELECT status, attempt_count, provider_attempt_started_at, provider_request_id
                FROM idempotency_operations
                WHERE business_scope_id = $1
                  AND operation_type = 'paid_model_invocation'
                """,
                request.operation_id,
            )
        finally:
            await connection.close()
        assert row is not None
        assert row["status"] == "ambiguous"
        assert int(row["attempt_count"]) == 1
        assert row["provider_attempt_started_at"] is not None
        assert row["provider_request_id"] is None
    finally:
        await _cleanup(request.operation_id)


def test_unknown_delivery_is_persistently_fail_closed() -> None:
    run(_unknown_delivery_is_persistently_fail_closed())


async def _provider_model_scope_supports_cross_provider_fallback_identity() -> None:
    request = _request()
    guard = PostgresModelPaidInvocationGuard(_asyncpg_dsn())
    calls: list[str] = []

    async def provider_a() -> ModelResult:
        calls.append("provider-a")
        result = _result(provider_request_id="provider-a-request")
        return ModelResult(
            status=result.status,
            provider="provider-a",
            model="model-a",
            provider_request_id=result.provider_request_id,
            outputs=result.outputs,
            usage=result.usage,
            timing=result.timing,
            cost=result.cost,
            safety_metadata=result.safety_metadata,
            finish_reason=result.finish_reason,
        )

    async def provider_b() -> ModelResult:
        calls.append("provider-b")
        result = _result(provider_request_id="provider-b-request")
        return ModelResult(
            status=result.status,
            provider="provider-b",
            model="model-b",
            provider_request_id=result.provider_request_id,
            outputs=result.outputs,
            usage=result.usage,
            timing=result.timing,
            cost=result.cost,
            safety_metadata=result.safety_metadata,
            finish_reason=result.finish_reason,
        )

    try:
        first = await guard.execute(
            request=request,
            provider="provider-a",
            model="model-a",
            invoke=provider_a,
        )
        second = await guard.execute(
            request=request,
            provider="provider-b",
            model="model-b",
            invoke=provider_b,
        )
        assert first.provider == "provider-a"
        assert second.provider == "provider-b"
        assert calls == ["provider-a", "provider-b"]

        connection = await asyncpg.connect(_asyncpg_dsn())
        try:
            count = await connection.fetchval(
                """
                SELECT count(*)
                FROM idempotency_operations
                WHERE business_scope_id = $1
                  AND operation_type = 'paid_model_invocation'
                """,
                request.operation_id,
            )
        finally:
            await connection.close()
        assert int(count) == 2
    finally:
        await _cleanup(request.operation_id)


def test_provider_model_scope_supports_cross_provider_fallback_identity() -> None:
    run(_provider_model_scope_supports_cross_provider_fallback_identity())


async def _changed_semantics_on_same_paid_identity_fails_closed() -> None:
    operation_id = uuid4()
    first_request = _request(operation_id, prompt="first")
    changed_request = _request(operation_id, prompt="changed")
    guard = PostgresModelPaidInvocationGuard(_asyncpg_dsn())
    provider_calls = 0

    async def first_invoke() -> ModelResult:
        nonlocal provider_calls
        provider_calls += 1
        return _result()

    async def must_not_run() -> ModelResult:
        nonlocal provider_calls
        provider_calls += 1
        raise AssertionError("semantic conflict reached provider")

    try:
        await guard.execute(
            request=first_request,
            provider=_PROVIDER,
            model=_MODEL,
            invoke=first_invoke,
        )
        with pytest.raises(ProviderInvocationError) as conflict:
            await guard.execute(
                request=changed_request,
                provider=_PROVIDER,
                model=_MODEL,
                invoke=must_not_run,
            )
        assert conflict.value.delivery_state == DeliveryState.UNKNOWN
        assert provider_calls == 1
    finally:
        await _cleanup(operation_id)


def test_changed_semantics_on_same_paid_identity_fails_closed() -> None:
    run(_changed_semantics_on_same_paid_identity_fails_closed())
