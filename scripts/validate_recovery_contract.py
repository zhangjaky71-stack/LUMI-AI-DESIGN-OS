#!/usr/bin/env python3
from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from lumi_api.recovery import (  # noqa: E402
    AgentRunRecoverySnapshot,
    OperationRecoverySnapshot,
    OutboxRecoverySnapshot,
    RecoveryAction,
    TaskRecoverySnapshot,
    plan_agent_run_recovery,
    plan_operation_recovery,
    plan_outbox_recovery,
    plan_task_recovery,
)

NOW = datetime(2026, 8, 15, 10, 0, tzinfo=UTC)

REQUIRED_PATHS = (
    "infra/compose/docker-compose.recovery.yml",
    "infra/docker/postgres-recovery/Dockerfile",
    "infra/docker/postgres-recovery/backup.sh",
    "infra/docker/postgres-recovery/primary-entrypoint.sh",
    "infra/docker/postgres-recovery/restore-entrypoint.sh",
    "infra/recovery/sql/verify_restored_database.sql",
    "infra/recovery/sql/recovery_workload.sql",
    "scripts/recovery-postgres-drill",
    "scripts/recovery-db-verify",
    "scripts/recovery-workload-report",
    "docs/runbooks/db-restore.md",
    "docs/runbooks/object-recovery.md",
    "docs/runbooks/queue-rebuild.md",
    "docs/runbooks/agent-run-reconciliation.md",
    "docs/runbooks/bad-deploy-rollback.md",
    "docs/runbooks/provider-outage.md",
    "docs/runbooks/security-incident.md",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate_files() -> None:
    missing = [path for path in REQUIRED_PATHS if not (ROOT / path).is_file()]
    require(not missing, f"missing recovery contract files: {missing}")


def validate_fail_closed_planner() -> None:
    ambiguous = plan_operation_recovery(
        OperationRecoverySnapshot(
            status="ambiguous",
            provider_request_id="provider-native-id",
            ambiguity_reason="process died after provider send",
        ),
        now=NOW,
    )
    require(ambiguous.action is RecoveryAction.MANUAL_REVIEW, "ambiguous operation must be manual")
    require(not ambiguous.automatic, "ambiguous operation must never be automatic")
    require(ambiguous.stop_auto_retry, "ambiguous operation must stop automatic retry")

    provider_sent = plan_operation_recovery(
        OperationRecoverySnapshot(
            status="in_progress",
            provider_request_id="provider-native-id",
            lease_expires_at=NOW - timedelta(minutes=10),
        ),
        now=NOW,
    )
    require(
        provider_sent.action is RecoveryAction.RECONCILE_EXTERNAL,
        "provider request must reconcile before retry",
    )
    require(provider_sent.stop_auto_retry, "provider request must stop automatic retry")

    local_task = plan_task_recovery(
        TaskRecoverySnapshot(
            status="running",
            lease_expires_at=NOW - timedelta(minutes=1),
        ),
        now=NOW,
    )
    require(local_task.action is RecoveryAction.SAFE_REQUEUE, "expired local-only task should requeue")

    external_task = plan_task_recovery(
        TaskRecoverySnapshot(status="running", external_ref="provider/job/42"),
        now=NOW,
    )
    require(
        external_task.action is RecoveryAction.RECONCILE_EXTERNAL,
        "external task must reconcile instead of blind requeue",
    )
    require(external_task.stop_auto_retry, "external task must stop automatic retry")

    resumable = plan_agent_run_recovery(
        AgentRunRecoverySnapshot(control_status="interrupted", checkpoint_id="checkpoint-7"),
        now=NOW,
    )
    require(resumable.action is RecoveryAction.RESUME_CHECKPOINT, "durable checkpoint must resume")

    published = plan_outbox_recovery(
        OutboxRecoverySnapshot(event_id="event-7", published_at=NOW),
        broker_rebuild_mode=True,
    )
    require(published.action is RecoveryAction.REPLAY_EVENT, "broker rebuild must replay persisted event")
    require("same event id" in published.reason, "replay must preserve the event id for inbox dedupe")


def main() -> int:
    validate_files()
    validate_fail_closed_planner()
    print("[recovery-contract] PASS: required files and fail-closed recovery decisions verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
