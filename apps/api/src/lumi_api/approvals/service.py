from __future__ import annotations

from datetime import datetime
from uuid import UUID

from .contracts import (
    ApprovalAuditEntry,
    ApprovalDecision,
    ApprovalDecisionCommand,
    ApprovalDecisionKind,
    ApprovalEffect,
    ApprovalRecord,
    ApprovalStatus,
    ArtifactApprovalRequest,
)
from .repository import PostgresApprovalRepository


class ApprovalService:
    def __init__(self, repository: PostgresApprovalRepository) -> None:
        self.repository = repository

    def request_artifact_approval(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        request_operation_id: UUID,
        artifact_version_id: UUID,
        requested_by: str,
        payload_summary: dict,
        expires_at: datetime | None,
        agent_run_id: UUID | None,
        task_id: UUID | None,
        interrupt_id: str | None,
        resume_version: int | None,
        requested_at: datetime,
    ) -> ApprovalRecord:
        return self.repository.create_artifact_approval(
            ArtifactApprovalRequest(
                organization_id=organization_id,
                project_id=project_id,
                request_operation_id=request_operation_id,
                artifact_version_id=artifact_version_id,
                requested_by=requested_by,
                payload_summary=payload_summary,
                expires_at=expires_at,
                agent_run_id=agent_run_id,
                task_id=task_id,
                interrupt_id=interrupt_id,
                resume_version=resume_version,
                requested_at=requested_at,
            )
        )

    def get(
        self, *, organization_id: UUID, approval_id: UUID, actor_id: str
    ) -> ApprovalRecord:
        return self.repository.get(organization_id, approval_id, actor_id)

    def list_project(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        actor_id: str,
        status: ApprovalStatus | None,
        limit: int,
    ) -> tuple[ApprovalRecord, ...]:
        return self.repository.list_project(
            organization_id=organization_id,
            project_id=project_id,
            actor_id=actor_id,
            status=status,
            limit=limit,
        )

    def decide(
        self,
        *,
        organization_id: UUID,
        approval_id: UUID,
        operation_id: UUID,
        decision: ApprovalDecisionKind,
        actor_id: str,
        actor_permissions: tuple[str, ...],
        reason: str | None,
        feedback: dict,
        decided_at: datetime,
    ) -> tuple[ApprovalRecord, ApprovalDecision, tuple[ApprovalEffect, ...]]:
        return self.repository.decide(
            ApprovalDecisionCommand(
                organization_id=organization_id,
                approval_id=approval_id,
                operation_id=operation_id,
                decision=decision,
                actor_id=actor_id,
                actor_permissions=actor_permissions,
                reason=reason,
                feedback=feedback,
                decided_at=decided_at,
            )
        )

    def list_audit(
        self, *, organization_id: UUID, approval_id: UUID, actor_id: str
    ) -> tuple[ApprovalAuditEntry, ...]:
        return self.repository.list_audit(
            organization_id=organization_id,
            approval_id=approval_id,
            actor_id=actor_id,
        )

    def list_effects(
        self, *, organization_id: UUID, approval_id: UUID, actor_id: str
    ) -> tuple[ApprovalEffect, ...]:
        self.repository.get(organization_id, approval_id, actor_id)
        return self.repository.list_effects(organization_id, approval_id)
