from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(path: str, *needles: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            raise SystemExit(f"{path}: missing NODE-20 contract marker: {needle}")


def forbid(path: str, *needles: str) -> None:
    text = (ROOT / path).read_text(encoding="utf-8")
    for needle in needles:
        if needle in text:
            raise SystemExit(f"{path}: forbidden NODE-20 contract marker: {needle}")


def main() -> int:
    require(
        "apps/api/alembic/versions/0009_idempotency_side_effects.py",
        "uq_idempotency_operations_identity",
        "lease_expires_at",
        "provider_request_id",
        "response_status",
        "ambiguity_reason",
        "uq_cost_ledger_operation_entry",
    )
    require(
        "apps/api/alembic/versions/0019_side_effect_provider_attempt_barrier.py",
        'down_revision = "0018_platform_provider_cost_guard"',
        "ADD COLUMN provider_attempt_started_at timestamptz",
        "DROP COLUMN provider_attempt_started_at",
    )
    require(
        "apps/api/alembic/versions/0011_cost_ledger_budget_quota.py",
        "ALTER TABLE cost_ledger DROP CONSTRAINT uq_cost_ledger_operation_entry",
        "uq_cost_ledger_operation_entry_key",
    )
    require(
        "apps/api/src/lumi_api/persistence/models/platform.py",
        "provider_attempt_started_at: Mapped[datetime | None]",
    )
    require(
        "apps/api/src/lumi_api/idempotency/contracts.py",
        "canonical_request_hash",
        "deterministic_operation_key",
        'AMBIGUOUS = "ambiguous"',
        'UNKNOWN = "unknown"',
    )
    require(
        "apps/api/src/lumi_api/idempotency/gateway.py",
        "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST",
        "ON CONFLICT (organization_id, operation_type, idempotency_key)",
        "ClaimDecision.RECONCILE",
        "async def mark_provider_attempt_started(",
        "provider_attempt_started_at = COALESCE(provider_attempt_started_at, now())",
        "PROVIDER_ATTEMPT_OUTCOME_UNKNOWN",
        "re-execution is forbidden",
        "clear_provider_attempt=True",
        "provider_reconciliation_total",
        "ambiguous_side_effect_total",
        "duplicate_prevented_total",
    )
    require(
        "apps/api/src/lumi_api/idempotency/ledger.py",
        "ON CONFLICT ON CONSTRAINT uq_cost_ledger_operation_entry_key DO NOTHING",
        "LedgerConflictError",
        'entry_key: str = "primary"',
    )
    require(
        "apps/api/src/lumi_api/idempotency/policy.py",
        "PAID_MODEL_INVOCATION",
        "IMAGE_GENERATION",
        "VIDEO_GENERATION",
        "BILLING_CHARGE",
        "EXTERNAL_PUBLISH",
    )
    require(
        "scripts/integration_idempotency_side_effects.py",
        "provider_attempt_without_request_id_fails_closed",
        "mark_provider_attempt_started",
        "PROVIDER_ATTEMPT_OUTCOME_UNKNOWN",
        "provider_calls == 0",
        "proven_not_accepted_allows_safe_retry",
    )
    require(
        "apps/worker-media/src/lumi_worker_media/app.py",
        "task_acks_late=False",
        "task_reject_on_worker_lost=False",
    )
    forbid(
        "apps/worker-media/src/lumi_worker_media/app.py",
        "task_acks_late=True",
        "task_reject_on_worker_lost=True",
    )
    print("NODE-20 idempotency/side-effect static contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
