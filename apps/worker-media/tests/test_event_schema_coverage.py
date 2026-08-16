from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from lumi_worker_media.event_runtime import validate_event_envelope

NOW = datetime(2026, 8, 16, 9, 15, tzinfo=UTC)
ORG = UUID("01910000-0000-7000-8000-000000000001")
PROJECT = UUID("01910000-0000-7000-8000-000000000031")
WORKSPACE = UUID("01910000-0000-7000-8000-000000000021")


def uid(suffix: int) -> str:
    return str(UUID(f"01910000-0000-7000-8000-{suffix:012d}"))


def envelope(event_type: str, aggregate_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    aggregate_id = PROJECT if aggregate_type == "project" else UUID(uid(900))
    return {
        "spec_version": "lumi.events/1.0",
        "event_id": uid(901),
        "event_type": event_type,
        "occurred_at": NOW.isoformat(),
        "organization_id": str(ORG),
        "aggregate_type": aggregate_type,
        "aggregate_id": str(aggregate_id),
        "aggregate_version": 1,
        "producer": "lumi.schema-coverage",
        "payload": payload,
    }


def test_all_node12_v1_payload_contracts_accept_valid_examples() -> None:
    fixtures = (
        envelope(
            "lumi.project.created.v1",
            "project",
            {
                "project_id": str(PROJECT),
                "workspace_id": str(WORKSPACE),
                "project_version": 1,
            },
        ),
        envelope(
            "lumi.asset.ready.v1",
            "asset",
            {
                "asset_id": uid(902),
                "project_id": str(PROJECT),
                "mime_type": "image/png",
                "checksum_sha256": "a" * 64,
            },
        ),
        envelope(
            "lumi.agent_run.started.v1",
            "agent_run",
            {
                "agent_run_id": uid(903),
                "project_id": str(PROJECT),
                "thread_id": "thread-human-readable-not-a-uuid",
                "graph_version": "graph-v1",
                "agent_config_version": "config-v1",
            },
        ),
        envelope(
            "lumi.agent_run.waiting_user.v1",
            "agent_run",
            {
                "agent_run_id": uid(904),
                "project_id": str(PROJECT),
                "interaction_id": uid(905),
                "reason_code": "approval_required",
            },
        ),
        envelope(
            "lumi.task.succeeded.v1",
            "task",
            {
                "task_id": uid(906),
                "project_id": str(PROJECT),
                "output_artifact_version_ids": [uid(907)],
            },
        ),
        envelope(
            "lumi.generation.completed.v1",
            "generation",
            {
                "generation_id": uid(908),
                "project_id": str(PROJECT),
                "operation_id": uid(909),
                "provider": "provider",
                "model": "model-v1",
                "output_artifact_version_ids": [uid(910)],
            },
        ),
        envelope(
            "lumi.artifact.version_created.v1",
            "artifact",
            {
                "artifact_id": uid(911),
                "artifact_version_id": uid(912),
                "branch_id": uid(913),
                "version_number": 1,
            },
        ),
        envelope(
            "lumi.artifact.approved.v1",
            "artifact",
            {
                "artifact_version_id": uid(914),
                "approval_id": uid(915),
                "actor_id": uid(916),
            },
        ),
        envelope(
            "lumi.cost.recorded.v1",
            "cost_entry",
            {
                "cost_entry_id": uid(917),
                "operation_id": uid(918),
                "amount": "1.25000000",
                "currency": "USD",
                "kind": "charge",
            },
        ),
    )
    assert len(fixtures) == 9
    assert [validate_event_envelope(item).event_type for item in fixtures] == [
        item["event_type"] for item in fixtures
    ]
