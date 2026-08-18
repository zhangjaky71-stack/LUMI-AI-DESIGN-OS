from __future__ import annotations

import inspect
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from lumi_api.api.v1 import approval_routes
from lumi_api.api.v1.approval_schemas import (
    ApprovalEffectResponse,
    ApprovalResponse,
    CreateArtifactApprovalRequest,
)
from lumi_api.api.v1.artifact_engine_schemas import ApproveVersionRequest
from lumi_api.approvals import (
    ApprovalDecisionKind,
    ApprovalPolicyMode,
    ApprovalRecord,
    ApprovalStatus,
    ApprovalType,
)
from lumi_api.approvals.repository import PostgresApprovalRepository
from lumi_api.auth import Permission
from lumi_api.persistence.models_approvals import (
    ApprovalAuditModel,
    ApprovalDecisionModel,
    ApprovalEffectModel,
    ApprovalRequestModel,
)


def _approval(**updates: object) -> ApprovalRecord:
    artifact_version_id = uuid4()
    values: dict[str, object] = {
        "id": uuid4(),
        "organization_id": uuid4(),
        "project_id": uuid4(),
        "request_operation_id": uuid4(),
        "approval_type": ApprovalType.ARTIFACT_VERSION,
        "subject_type": "ARTIFACT_VERSION",
        "subject_id": artifact_version_id,
        "subject_version_ref": "artifact:v3",
        "subject_snapshot_hash": "a" * 64,
        "artifact_version_id": artifact_version_id,
        "status": ApprovalStatus.PENDING,
        "requested_by": str(uuid4()),
        "required_permission": Permission.ARTIFACT_APPROVE.value,
        "policy_mode": ApprovalPolicyMode.ANY_ONE,
        "policy_version": 1,
        "min_approvals": 1,
        "payload_summary": {"title": "Approve v3", "summary": "Exact review"},
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "version": 1,
    }
    values.update(updates)
    return ApprovalRecord.model_validate(values)


def test_artifact_approval_requires_exact_subject_and_snapshot_hash() -> None:
    valid = _approval()
    assert valid.subject_id == valid.artifact_version_id
    assert valid.subject_snapshot_hash == "a" * 64

    with pytest.raises(ValidationError):
        _approval(subject_id=uuid4())
    with pytest.raises(ValidationError):
        _approval(subject_snapshot_hash=None)


def test_public_create_schema_cannot_forge_graph_bridge() -> None:
    fields = CreateArtifactApprovalRequest.model_fields
    assert set(fields) == {"artifact_version_id", "title", "summary", "expires_at"}
    for forbidden in ("agent_run_id", "task_id", "interrupt_id", "resume_version"):
        assert forbidden not in fields


def test_public_approval_and_effect_responses_exclude_runtime_internals() -> None:
    approval_fields = ApprovalResponse.model_fields
    effect_fields = ApprovalEffectResponse.model_fields
    assert "interrupt_id" not in approval_fields
    assert "resume_version" not in approval_fields
    assert "payload" not in effect_fields
    assert "payload_json" not in effect_fields
    assert "last_error" not in effect_fields
    assert "has_error" in effect_fields


def test_legacy_direct_artifact_approval_cannot_accept_client_approver() -> None:
    assert "approved_by_id" not in ApproveVersionRequest.model_fields
    with pytest.raises(ValidationError):
        ApproveVersionRequest.model_validate(
            {"approved_by_id": str(uuid4()), "validation_ref": "legacy"}
        )
    request = ApproveVersionRequest(validation_ref="legacy")
    with pytest.raises(ValueError, match="DIRECT_ARTIFACT_APPROVAL_DISABLED"):
        _ = request.approved_by_id


def test_formal_decision_uses_authenticated_actor_permissions() -> None:
    source = inspect.getsource(approval_routes.decide_approval)
    repository_source = inspect.getsource(PostgresApprovalRepository.decide)
    assert "actor_id, permissions = _context(request)" in source
    assert "actor_permissions=permissions" in source
    assert "required_permission not in command.actor_permissions" in repository_source
    assert "APPROVAL_PERMISSION_REQUIRED" in repository_source
    assert Permission.ARTIFACT_APPROVE.value == "artifact.approve"


def test_exact_version_stale_check_does_not_follow_branch_head() -> None:
    source = inspect.getsource(PostgresApprovalRepository._artifact_stale_code)
    assert "subject_snapshot_hash" in source
    assert 'row["status"] != "READY"' in source
    for forbidden in ("head_version_id", "artifact_branches", "current_head", "latest_version"):
        assert forbidden not in source


def test_request_and_decision_are_tenant_scoped_idempotent() -> None:
    request_constraints = {constraint.name for constraint in ApprovalRequestModel.__table__.constraints}
    decision_constraints = {constraint.name for constraint in ApprovalDecisionModel.__table__.constraints}
    effect_constraints = {constraint.name for constraint in ApprovalEffectModel.__table__.constraints}
    assert "uq_approval_request_operation" in request_constraints
    assert "uq_approval_decision_operation" in decision_constraints
    assert "uq_approval_effect_operation" in effect_constraints
    assert "uq_approval_effect_type" in effect_constraints


def test_approval_domain_keeps_decision_audit_and_effects_separate() -> None:
    assert ApprovalRequestModel.__tablename__ == "approval_requests"
    assert ApprovalDecisionModel.__tablename__ == "approval_decisions"
    assert ApprovalAuditModel.__tablename__ == "approval_audit_events"
    assert ApprovalEffectModel.__tablename__ == "approval_effects"


def test_non_approval_decision_requires_feedback() -> None:
    from lumi_api.approvals.contracts import ApprovalDecision

    with pytest.raises(ValidationError):
        ApprovalDecision(
            id=uuid4(),
            organization_id=uuid4(),
            approval_id=uuid4(),
            operation_id=uuid4(),
            decision=ApprovalDecisionKind.REJECTED,
            actor_id=str(uuid4()),
            approval_version=2,
            created_at=datetime.now(UTC),
        )


def test_audit_route_requires_admin_audit_permission() -> None:
    source = inspect.getsource(approval_routes.list_approval_audit)
    assert '"admin.audit.read" not in permissions' in source
    assert "approval_audit_permission_required" in source
