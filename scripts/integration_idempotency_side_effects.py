from __future__ import annotations

import asyncio
import os
from collections import Counter
from decimal import Decimal
from uuid import UUID, uuid4

import asyncpg

from lumi_api.idempotency import (
    ClaimDecision,
    CostLedgerEntry,
    CostLedgerGateway,
    IdempotencyConflictError,
    IdempotencyContext,
    ProviderReconciliation,
    ProviderState,
    SideEffectGateway,
    SideEffectResult,
)


class Metrics:
    def __init__(self) -> None:
        self.values: Counter[str] = Counter()

    def increment(self, metric: str, value: int = 1) -> None:
        self.values[metric] += value


class Reconciler:
    def __init__(self, outcome: ProviderReconciliation) -> None:
        self.outcome = outcome
        self.calls = 0

    async def lookup(self, provider_request_id: str) -> ProviderReconciliation:
        assert provider_request_id
        self.calls += 1
        return self.outcome


def dsn() -> str:
    value = os.environ["DATABASE_URL"]
    return value.replace("postgresql+asyncpg://", "postgresql://", 1)


async def organization_id() -> UUID:
    connection = await asyncpg.connect(dsn())
    try:
        value = await connection.fetchval(
            "SELECT id FROM organizations ORDER BY created_at LIMIT 1"
        )
        if value is None:
            raise RuntimeError("seeded organization required")
        return value
    finally:
        await connection.close()


async def expire_lease(operation_id: UUID) -> None:
    connection = await asyncpg.connect(dsn())
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


async def concurrent_claim_test(gateway: SideEffectGateway, org_id: UUID) -> UUID:
    context = IdempotencyContext(
        organization_id=org_id,
        operation_type="image.generate",
        idempotency_key=f"concurrent-{uuid4()}",
        request={"prompt": "one operation", "size": "1024x1024"},
        business_scope_id=uuid4(),
        lease_seconds=30,
    )
    claims = await asyncio.gather(
        *(gateway.claim(context, lease_owner=f"worker-{index}") for index in range(12))
    )
    decisions = Counter(claim.decision for claim in claims)
    assert decisions[ClaimDecision.EXECUTE] == 1, decisions
    assert decisions[ClaimDecision.WAIT] == 11, decisions
    execute_claim = next(
        claim for claim in claims if claim.decision == ClaimDecision.EXECUTE
    )
    await gateway.succeed(
        execute_claim.snapshot.id,
        lease_owner=execute_claim.snapshot.lease_owner or "",
        result=SideEffectResult(
            result_ref="asset://one",
            result_json={"asset_id": "one"},
            response_status=201,
        ),
    )
    replay = await gateway.claim(context, lease_owner="client-retry")
    assert replay.decision == ClaimDecision.REPLAY
    assert replay.snapshot.result_ref == "asset://one"
    return replay.snapshot.id


async def different_request_conflict_test(
    gateway: SideEffectGateway,
    org_id: UUID,
) -> None:
    key = f"conflict-{uuid4()}"
    original = IdempotencyContext(org_id, "export.create", key, {"format": "pdf"})
    await gateway.claim(original, lease_owner="owner-a")
    changed = IdempotencyContext(org_id, "export.create", key, {"format": "png"})
    try:
        await gateway.claim(changed, lease_owner="owner-b")
    except IdempotencyConflictError as exc:
        assert exc.code == "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST"
    else:
        raise AssertionError("same key with different request must conflict")


async def provider_crash_window_test(
    gateway: SideEffectGateway,
    org_id: UUID,
) -> None:
    context = IdempotencyContext(
        org_id,
        "video.generate",
        f"provider-crash-{uuid4()}",
        {"prompt": "crash-window"},
        lease_seconds=5,
    )
    first = await gateway.claim(context, lease_owner="crashed-worker")
    assert first.decision == ClaimDecision.EXECUTE
    await gateway.record_provider_request(
        first.snapshot.id,
        lease_owner="crashed-worker",
        provider_request_id="provider-job-123",
    )
    await expire_lease(first.snapshot.id)
    recovery = await gateway.claim(context, lease_owner="recovery-worker")
    assert recovery.decision == ClaimDecision.RECONCILE
    reconciler = Reconciler(
        ProviderReconciliation(
            state=ProviderState.SUCCEEDED,
            result_ref="asset://provider-result",
            result_json={"provider": "already-finished"},
            response_status=201,
        )
    )
    recovered = await gateway.reconcile(recovery, reconciler=reconciler)
    assert recovered.decision == ClaimDecision.REPLAY
    assert recovered.snapshot.result_ref == "asset://provider-result"
    assert reconciler.calls == 1
    assert recovered.snapshot.attempt_count == 2


async def provider_confirmed_failure_allows_retry(
    gateway: SideEffectGateway,
    org_id: UUID,
) -> None:
    context = IdempotencyContext(
        org_id,
        "image.generate",
        f"provider-failed-{uuid4()}",
        {"prompt": "safe retry"},
        lease_seconds=5,
    )
    first = await gateway.claim(context, lease_owner="worker-a")
    await gateway.record_provider_request(
        first.snapshot.id,
        lease_owner="worker-a",
        provider_request_id="provider-job-failed",
    )
    await expire_lease(first.snapshot.id)
    recovery = await gateway.claim(context, lease_owner="worker-b")
    reconciler = Reconciler(ProviderReconciliation(state=ProviderState.FAILED))
    decision = await gateway.reconcile(recovery, reconciler=reconciler)
    assert decision.decision == ClaimDecision.RETRY_SAFE
    retry = await gateway.claim(context, lease_owner="worker-c")
    assert retry.decision == ClaimDecision.EXECUTE
    assert retry.snapshot.provider_request_id is None


async def ambiguous_provider_state_blocks_retry(
    gateway: SideEffectGateway,
    org_id: UUID,
) -> None:
    context = IdempotencyContext(
        org_id,
        "external.publish",
        f"ambiguous-{uuid4()}",
        {"target": "remote"},
        lease_seconds=5,
    )
    first = await gateway.claim(context, lease_owner="worker-a")
    await gateway.record_provider_request(
        first.snapshot.id,
        lease_owner="worker-a",
        provider_request_id="provider-unknown",
    )
    await expire_lease(first.snapshot.id)
    recovery = await gateway.claim(context, lease_owner="worker-b")
    reconciler = Reconciler(
        ProviderReconciliation(
            state=ProviderState.UNKNOWN,
            detail="provider has no status API",
        )
    )
    ambiguous = await gateway.reconcile(recovery, reconciler=reconciler)
    assert ambiguous.decision == ClaimDecision.AMBIGUOUS
    blocked = await gateway.claim(context, lease_owner="worker-c")
    assert blocked.decision == ClaimDecision.AMBIGUOUS


async def cost_ledger_dedupe_test(org_id: UUID, operation_id: UUID) -> None:
    ledger = CostLedgerGateway(dsn())
    entry = CostLedgerEntry(
        organization_id=org_id,
        operation_id=operation_id,
        entry_type="provider_charge",
        amount=Decimal("1.25000000"),
        currency="USD",
        provider="test-provider",
        model="test-model",
        metadata_json={"source": "node20-failure-injection"},
    )
    results = await asyncio.gather(
        ledger.record_once(entry),
        ledger.record_once(entry),
    )
    assert sum(1 for _, created in results if created) == 1
    assert results[0][0] == results[1][0]
    connection = await asyncpg.connect(dsn())
    try:
        count = await connection.fetchval(
            """
            SELECT count(*) FROM cost_ledger
            WHERE operation_id = $1 AND entry_type = 'provider_charge'
            """,
            operation_id,
        )
        assert int(count) == 1
    finally:
        await connection.close()


async def execute_replay_test(gateway: SideEffectGateway, org_id: UUID) -> None:
    context = IdempotencyContext(
        org_id,
        "email.send",
        f"execute-{uuid4()}",
        {"template": "invite", "recipient_ref": "user-1"},
    )
    calls = 0

    async def invoke(handle: object) -> SideEffectResult:
        nonlocal calls
        del handle
        calls += 1
        return SideEffectResult(
            result_ref="message://1",
            result_json={"sent": True},
            response_status=202,
        )

    first = await gateway.execute(
        context,
        lease_owner="http-request-1",
        invoke=invoke,
    )
    second = await gateway.execute(
        context,
        lease_owner="http-request-2",
        invoke=invoke,
    )
    assert first.replayed is False
    assert second.replayed is True
    assert calls == 1


async def main_async() -> None:
    org_id = await organization_id()
    metrics = Metrics()
    gateway = SideEffectGateway(dsn(), metrics=metrics)
    operation_id = await concurrent_claim_test(gateway, org_id)
    await different_request_conflict_test(gateway, org_id)
    await provider_crash_window_test(gateway, org_id)
    await provider_confirmed_failure_allows_retry(gateway, org_id)
    await ambiguous_provider_state_blocks_retry(gateway, org_id)
    await cost_ledger_dedupe_test(org_id, operation_id)
    await execute_replay_test(gateway, org_id)
    assert metrics.values["duplicate_prevented_total"] >= 1
    assert metrics.values["idempotency_replay_total"] >= 1
    assert metrics.values["idempotency_conflict_total"] >= 1
    assert metrics.values["stale_lease_total"] >= 1
    assert metrics.values["provider_reconciliation_total"] >= 1
    assert metrics.values["ambiguous_side_effect_total"] >= 1


def main() -> int:
    asyncio.run(main_async())
    print("NODE-20 idempotency/side-effect failure injection: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
