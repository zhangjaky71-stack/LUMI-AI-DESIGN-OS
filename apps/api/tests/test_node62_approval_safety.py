from __future__ import annotations

import inspect
from dataclasses import dataclass
from uuid import uuid4

import pytest

from lumi_api.api.v1 import approval_routes
from lumi_api.approvals import ApprovalDecisionKind
from lumi_api.approvals.adapters import AgentRunApprovalResumeAdapter
from lumi_api.approvals.effects import ApprovalEffectProcessor
from lumi_api.approvals.repository import PostgresApprovalRepository
from lumi_api.persistence.models_approvals import (
    ApprovalAuditModel,
    ApprovalDecisionModel,
    ApprovalEffectModel,
    ApprovalRequestModel,
)


def test_migration_chain_is_linear_and_tables_are_durable() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    migration = (root / "apps/api/migrations/versions/20260818_0022_approval_engine.py").read_text(encoding="utf-8")
    up_sql = (root / "apps/api/migrations/versions/20260818_0022_sql/up.sql").read_text(encoding="utf-8")
    assert 'revision = "20260818_0022"' in migration
    assert 'down_revision = "20260818_0021"' in migration
    for table in ("approval_requests", "approval_decisions", "approval_audit_events", "approval_effects"):
        assert f"CREATE TABLE {table}" in up_sql


def test_approval_outbox_payloads_are_id_only_and_do_not_copy_feedback() -> None:
    source = inspect.getsource(PostgresApprovalRepository._insert_outbox)
    creation_source = inspect.getsource(PostgresApprovalRepository.create_artifact_approval)
    decision_source = inspect.getsource(PostgresApprovalRepository.decide)
    assert "payload_json" in source
    assert '"approval_id"' in creation_source
    assert '"artifact_version_id"' in creation_source
    assert '"decision"' in decision_source
    # Feedback is stored in canonical decision/effect records, not copied to approval.decided Outbox.
    decided_payload = decision_source.split('event_type="approval.decided"', 1)[1].split("now=command.decided_at", 1)[0]
    assert "feedback" not in decided_payload
    assert "reason" not in decided_payload


def test_effects_are_retryable_durable_side_effects_not_decision_truth() -> None:
    source = inspect.getsource(ApprovalEffectProcessor.process)
    claim = inspect.getsource(ApprovalEffectProcessor._claim)
    assert "self._mark_completed" in source
    assert "self._mark_failed" in source
    assert "PENDING" in inspect.getsource(PostgresApprovalRepository._insert_effect)
    assert "attempt_count=attempt_count+1" in claim
    assert ApprovalRequestModel.__tablename__ != ApprovalEffectModel.__tablename__
    assert ApprovalDecisionModel.__tablename__ != ApprovalEffectModel.__tablename__
    assert ApprovalAuditModel.__tablename__ != ApprovalEffectModel.__tablename__


@dataclass
class _FakeRuntime:
    call: dict | None = None

    async def resume(self, **kwargs):
        self.call = kwargs
        return {"ok": True}


@pytest.mark.asyncio
async def test_agent_bridge_resumes_with_formal_approval_id_and_decision() -> None:
    runtime = _FakeRuntime()
    approval_id = uuid4()
    run_id = uuid4()
    operation_id = uuid4()
    organization_id = uuid4()
    adapter = AgentRunApprovalResumeAdapter(
        runtime,
        request_context_factory=lambda org, approval: {"organization_id": str(org), "approval_id": str(approval)},
    )

    await adapter.resume_from_approval(
        organization_id=organization_id,
        approval_id=approval_id,
        agent_run_id=run_id,
        operation_id=operation_id,
        resume_version=4,
        interrupt_id="interrupt-4",
        decision=ApprovalDecisionKind.CHANGES_REQUESTED,
        reason="Move the CTA",
        feedback={"node_ids": [str(uuid4())]},
    )

    assert runtime.call is not None
    assert runtime.call["kind"] == "approval"
    assert runtime.call["operation_id"] == operation_id
    assert runtime.call["value"]["approval_id"] == str(approval_id)
    assert runtime.call["value"]["decision"] == "CHANGES_REQUESTED"
    assert runtime.call["value"]["reason"] == "Move the CTA"


def test_public_approval_routes_do_not_accept_graph_bridge_fields() -> None:
    source = inspect.getsource(approval_routes.request_artifact_approval)
    assert "agent_run_id=None" in source
    assert "task_id=None" in source
    assert "interrupt_id=None" in source
    assert "resume_version=None" in source


def test_effect_api_projection_does_not_expose_internal_payload_or_error() -> None:
    source = inspect.getsource(approval_routes._effect_response)
    assert "payload" not in source
    assert "last_error=value.last_error" not in source
    assert "has_error=value.last_error is not None" in source
