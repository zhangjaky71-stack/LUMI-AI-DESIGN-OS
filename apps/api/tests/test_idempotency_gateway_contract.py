from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from lumi_api.idempotency import (
    AmbiguousSideEffect,
    CompensationMode,
    IdempotencyConflict,
    IdempotencyOperation,
    MemoryIdempotencyStore,
    MemoryMetrics,
    OperationInProgress,
    OperationRequest,
    ProviderReconciliation,
    ProviderReconciliationStatus,
    SideEffectGateway,
    SideEffectKind,
    SideEffectOutcome,
    canonical_request_hash,
    deterministic_operation_key,
)

NOW = datetime(2026, 8, 16, 9, 30, tzinfo=UTC)
ORG = UUID("01910000-0000-7000-8000-000000000001")
PROJECT = UUID("01910000-0000-7000-8000-000000000031")


def request(
    payload: dict[str, object] | None = None,
    *,
    key: str = "idem-node20-0001",
    operation_type: str = "generation.create",
    paid: bool = False,
    lease_seconds: int = 5,
) -> OperationRequest:
    body = payload or {"project_id": str(PROJECT), "prompt": "hello"}
    side_effect = (
        SideEffectKind.PAID_MODEL_INVOCATION
        if paid
        else SideEffectKind.GENERIC_WRITE
    )
    return OperationRequest(
        organization_id=ORG,
        operation_type=operation_type,
        idempotency_key=key,
        request_hash=canonical_request_hash(body),
        business_scope_id=str(PROJECT),
        side_effect_kind=side_effect,
        compensation_mode=CompensationMode.NON_COMPENSATABLE,
        paid=paid,
        lease_seconds=lease_seconds,
    )


def test_request_hash_is_stable_and_ignores_ephemeral_trace_fields() -> None:
    left = {
        "project_id": PROJECT,
        "prompt": "hello",
        "trace_id": "trace-a",
        "nested": {"request_id": "req-a", "value": 2},
    }
    right = {
        "nested": {"value": 2, "request_id": "req-b"},
        "prompt": "hello",
        "project_id": str(PROJECT),
        "trace_id": "trace-b",
    }
    assert canonical_request_hash(left) == canonical_request_hash(right)


def test_deterministic_operation_key_does_not_include_retry_attempt() -> None:
    one = deterministic_operation_key(
        organization_id=ORG,
        operation_type="generation.create",
        business_scope_id=str(PROJECT),
        logical_key="task-7:slot-2",
        policy_version="retry-v1",
    )
    two = deterministic_operation_key(
        organization_id=ORG,
        operation_type="generation.create",
        business_scope_id=str(PROJECT),
        logical_key="task-7:slot-2",
        policy_version="retry-v1",
    )
    assert one == two and one.startswith("op_")


def test_completed_operation_replays_without_second_effect() -> None:
    store = MemoryIdempotencyStore()
    metrics = MemoryMetrics()
    gateway = SideEffectGateway(store, metrics=metrics)
    calls = 0

    async def effect(_context):
        nonlocal calls
        calls += 1
        return SideEffectOutcome(
            result={"generation_id": "g-1"},
            response_status=202,
        )

    first = asyncio.run(
        gateway.execute(request(), effect, lease_owner="worker-a", now=NOW)
    )
    second = asyncio.run(
        gateway.execute(
            request(),
            effect,
            lease_owner="worker-b",
            now=NOW + timedelta(seconds=1),
        )
    )
    assert calls == 1
    assert first.replayed is False
    assert second.replayed is True
    assert second.result == {"generation_id": "g-1"}
    assert second.operation_id == first.operation_id
    assert metrics.values["idempotency_replay_total"] == 1
    assert metrics.values["duplicate_prevented_total"] == 1


def test_same_key_different_request_is_conflict() -> None:
    store = MemoryIdempotencyStore()
    gateway = SideEffectGateway(store)

    async def effect(_context):
        return SideEffectOutcome(result={"ok": True})

    asyncio.run(
        gateway.execute(request(), effect, lease_owner="worker-a", now=NOW)
    )
    changed = request({"project_id": str(PROJECT), "prompt": "different"})
    with pytest.raises(
        IdempotencyConflict,
        match="IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST",
    ):
        asyncio.run(
            gateway.execute(
                changed,
                effect,
                lease_owner="worker-b",
                now=NOW + timedelta(seconds=1),
            )
        )


def test_same_client_key_is_allowed_for_different_operation_types() -> None:
    store = MemoryIdempotencyStore()
    gateway = SideEffectGateway(store)
    calls = 0

    async def effect(_context):
        nonlocal calls
        calls += 1
        return SideEffectOutcome(result={"call": calls})

    asyncio.run(gateway.execute(request(), effect, lease_owner="one", now=NOW))
    asyncio.run(
        gateway.execute(
            request(operation_type="export.create"),
            effect,
            lease_owner="two",
            now=NOW,
        )
    )
    assert calls == 2


def test_two_concurrent_same_key_only_one_enters_business_effect() -> None:
    async def scenario() -> None:
        store = MemoryIdempotencyStore()
        gateway = SideEffectGateway(store)
        entered = asyncio.Event()
        release = asyncio.Event()
        calls = 0

        async def effect(_context):
            nonlocal calls
            calls += 1
            entered.set()
            await release.wait()
            return SideEffectOutcome(result={"ok": True})

        first = asyncio.create_task(
            gateway.execute(
                request(),
                effect,
                lease_owner="worker-a",
                now=NOW,
            )
        )
        await entered.wait()
        with pytest.raises(OperationInProgress):
            await gateway.execute(
                request(),
                effect,
                lease_owner="worker-b",
                now=NOW,
            )
        release.set()
        await first
        replay = await gateway.execute(
            request(),
            effect,
            lease_owner="worker-c",
            now=NOW + timedelta(seconds=1),
        )
        assert replay.replayed is True
        assert calls == 1

    asyncio.run(scenario())


def test_heartbeat_extends_lease_and_blocks_premature_recovery() -> None:
    async def scenario() -> None:
        store = MemoryIdempotencyStore()
        req = request(key="idem-heartbeat-0001", lease_seconds=5)
        acquired = await store.acquire(req, lease_owner="worker-a", now=NOW)
        operation = acquired.operation
        renewed = await store.renew_lease(
            ORG,
            operation.id,
            lease_owner="worker-a",
            lease_seconds=5,
            now=NOW + timedelta(seconds=4),
        )
        assert renewed.lease_expires_at == NOW + timedelta(seconds=9)
        contender = await store.acquire(
            req,
            lease_owner="worker-b",
            now=NOW + timedelta(seconds=6),
        )
        assert contender.action.value == "wait"
        assert contender.operation.lease_owner == "worker-a"

    asyncio.run(scenario())


def test_langgraph_resume_uses_same_business_key_and_replays() -> None:
    logical_key = deterministic_operation_key(
        organization_id=ORG,
        operation_type="graph.provider.generate",
        business_scope_id=str(PROJECT),
        logical_key="run-7:node-image:slot-1",
        policy_version="graph-v1",
    )
    req = request(
        key=logical_key,
        operation_type="graph.provider.generate",
    )
    store = MemoryIdempotencyStore()
    gateway = SideEffectGateway(store)
    calls = 0

    async def effect(_context):
        nonlocal calls
        calls += 1
        return SideEffectOutcome(result={"artifact_version_id": "v1"})

    first = asyncio.run(
        gateway.execute(req, effect, lease_owner="graph-before-interrupt", now=NOW)
    )
    resumed = asyncio.run(
        gateway.execute(
            req,
            effect,
            lease_owner="graph-after-resume",
            now=NOW + timedelta(seconds=1),
        )
    )
    assert first.operation_id == resumed.operation_id
    assert resumed.replayed is True
    assert calls == 1


class SimulatedHardCrash(BaseException):
    pass


class SuccessfulReconciler:
    def __init__(self) -> None:
        self.calls = 0

    async def reconcile(
        self,
        operation: IdempotencyOperation,
    ) -> ProviderReconciliation:
        self.calls += 1
        assert operation.provider_request_id == "provider-accepted-123"
        return ProviderReconciliation(
            status=ProviderReconciliationStatus.SUCCEEDED,
            provider_request_id="provider-accepted-123",
            response_status=200,
            result_ref="artifact-version:0191",
            result={"artifact_version_id": "0191"},
        )


def test_provider_success_then_process_crash_reconciles_without_second_paid_call() -> None:
    store = MemoryIdempotencyStore()
    metrics = MemoryMetrics()
    gateway = SideEffectGateway(store, metrics=metrics)
    provider_calls = 0

    async def crashing_effect(context):
        nonlocal provider_calls
        provider_calls += 1
        await context.record_provider_request(
            "provider-accepted-123",
            now=NOW,
        )
        raise SimulatedHardCrash(
            "process died after provider success before DB completion"
        )

    with pytest.raises(SimulatedHardCrash):
        asyncio.run(
            gateway.execute(
                request(paid=True),
                crashing_effect,
                lease_owner="worker-a",
                now=NOW,
            )
        )
    reconciler = SuccessfulReconciler()

    async def must_not_run(_context):
        raise AssertionError("paid provider call must not execute twice")

    recovered = asyncio.run(
        gateway.execute(
            request(paid=True),
            must_not_run,
            lease_owner="worker-b",
            reconciler=reconciler,
            now=NOW + timedelta(seconds=6),
        )
    )
    assert provider_calls == 1
    assert reconciler.calls == 1
    assert recovered.replayed is True
    assert recovered.result_ref == "artifact-version:0191"
    assert metrics.values["provider_reconciliation_total"] == 1
    assert metrics.values["stale_lease_total"] == 1


def test_paid_stale_lease_without_reconciler_fails_ambiguous_not_duplicate() -> None:
    store = MemoryIdempotencyStore()
    gateway = SideEffectGateway(store)
    provider_calls = 0

    async def crashing_effect(context):
        nonlocal provider_calls
        provider_calls += 1
        await context.record_provider_request(
            "provider-unknown-1",
            now=NOW,
        )
        raise SimulatedHardCrash()

    with pytest.raises(SimulatedHardCrash):
        asyncio.run(
            gateway.execute(
                request(paid=True),
                crashing_effect,
                lease_owner="one",
                now=NOW,
            )
        )
    with pytest.raises(AmbiguousSideEffect):
        asyncio.run(
            gateway.execute(
                request(paid=True),
                crashing_effect,
                lease_owner="two",
                now=NOW + timedelta(seconds=6),
            )
        )
    with pytest.raises(AmbiguousSideEffect):
        asyncio.run(
            gateway.execute(
                request(paid=True),
                crashing_effect,
                lease_owner="three",
                now=NOW + timedelta(seconds=12),
            )
        )
    assert provider_calls == 1
