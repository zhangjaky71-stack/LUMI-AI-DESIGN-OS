from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Iterator, Mapping
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from lumi_api.domain.ids import new_uuid7

from .contracts import (
    ApprovalAuditEntry,
    ApprovalDecision,
    ApprovalDecisionCommand,
    ApprovalDecisionKind,
    ApprovalEffect,
    ApprovalEffectStatus,
    ApprovalEffectType,
    ApprovalPolicyMode,
    ApprovalRecord,
    ApprovalStatus,
    ApprovalType,
    ArtifactApprovalRequest,
)


class ApprovalNotFound(RuntimeError):
    pass


class ApprovalForbidden(RuntimeError):
    pass


class ApprovalConflict(RuntimeError):
    pass


class ApprovalStale(RuntimeError):
    pass


class PostgresApprovalRepository:
    def __init__(self, session: Session, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        if self.session.in_transaction():
            self.session.rollback()
        with self.session.begin():
            yield

    def _assert_org(self, organization_id: UUID) -> None:
        if organization_id != self.organization_id:
            raise ApprovalNotFound("APPROVAL_RESOURCE_NOT_FOUND")

    @staticmethod
    def _actor_uuid(actor_id: str) -> UUID:
        try:
            return UUID(actor_id)
        except ValueError as exc:
            raise ApprovalForbidden("APPROVAL_USER_ACTOR_REQUIRED") from exc

    def require_project_access(
        self, *, organization_id: UUID, project_id: UUID, actor_id: str
    ) -> str:
        self._assert_org(organization_id)
        actor_uuid = self._actor_uuid(actor_id)
        row = self.session.execute(
            text(
                """
                SELECT p.created_by, pm.role AS project_role
                FROM projects p
                JOIN organization_members om
                  ON om.organization_id=p.organization_id
                 AND om.user_id=:actor_uuid
                LEFT JOIN project_members pm
                  ON pm.organization_id=p.organization_id
                 AND pm.project_id=p.id
                 AND pm.user_id=:actor_uuid
                WHERE p.id=:project_id
                  AND p.organization_id=:organization_id
                  AND p.deleted_at IS NULL
                """
            ),
            {
                "actor_uuid": actor_uuid,
                "project_id": project_id,
                "organization_id": organization_id,
            },
        ).mappings().one_or_none()
        if row is None:
            raise ApprovalNotFound("PROJECT_NOT_FOUND")
        if row["created_by"] == actor_uuid:
            return "admin"
        role = row["project_role"]
        if role not in {"admin", "editor", "viewer"}:
            raise ApprovalForbidden("PROJECT_MEMBERSHIP_REQUIRED")
        return str(role)

    def create_artifact_approval(self, command: ArtifactApprovalRequest) -> ApprovalRecord:
        self._assert_org(command.organization_id)
        existing = self._get_by_request_operation(
            command.organization_id, command.request_operation_id
        )
        if existing is not None:
            if (
                existing.project_id != command.project_id
                or existing.artifact_version_id != command.artifact_version_id
            ):
                raise ApprovalConflict("APPROVAL_REQUEST_OPERATION_CONFLICT")
            return existing

        now = command.requested_at
        approval_id = new_uuid7()
        with self._transaction():
            self.require_project_access(
                organization_id=command.organization_id,
                project_id=command.project_id,
                actor_id=command.requested_by,
            )
            artifact = self._artifact_snapshot(
                organization_id=command.organization_id,
                project_id=command.project_id,
                artifact_version_id=command.artifact_version_id,
                lock=False,
            )
            if artifact["status"] != "READY":
                raise ApprovalConflict("ARTIFACT_VERSION_NOT_READY_FOR_APPROVAL")
            self._validate_runtime_links(command)
            pending = self.session.execute(
                text(
                    """
                    SELECT * FROM approval_requests
                    WHERE organization_id=:organization_id
                      AND artifact_version_id=:artifact_version_id
                      AND approval_type='ARTIFACT_VERSION'
                      AND status='PENDING'
                    """
                ),
                {
                    "organization_id": command.organization_id,
                    "artifact_version_id": command.artifact_version_id,
                },
            ).mappings().one_or_none()
            if pending is not None:
                raise ApprovalConflict("ARTIFACT_APPROVAL_ALREADY_PENDING")
            self.session.execute(
                text(
                    """
                    INSERT INTO approval_requests (
                        id, organization_id, project_id, request_operation_id,
                        agent_run_id, task_id, approval_type, subject_type,
                        subject_id, subject_version_ref, subject_snapshot_hash,
                        artifact_version_id, status, requested_by, required_permission,
                        policy_mode, policy_version, min_approvals, payload_summary_json,
                        changes_requested_json, expires_at, interrupt_id, resume_version,
                        created_at, updated_at, version
                    ) VALUES (
                        :id, :organization_id, :project_id, :request_operation_id,
                        :agent_run_id, :task_id, 'ARTIFACT_VERSION', 'ARTIFACT_VERSION',
                        :subject_id, :subject_version_ref, :subject_snapshot_hash,
                        :artifact_version_id, 'PENDING', :requested_by, 'artifact.approve',
                        'ANY_ONE', 1, 1, CAST(:payload_summary AS jsonb), '{}'::jsonb,
                        :expires_at, :interrupt_id, :resume_version,
                        :created_at, :updated_at, 1
                    )
                    """
                ),
                {
                    "id": approval_id,
                    "organization_id": command.organization_id,
                    "project_id": command.project_id,
                    "request_operation_id": command.request_operation_id,
                    "agent_run_id": command.agent_run_id,
                    "task_id": command.task_id,
                    "subject_id": command.artifact_version_id,
                    "subject_version_ref": f"artifact:v{artifact['version_number']}",
                    "subject_snapshot_hash": artifact["content_hash"],
                    "artifact_version_id": command.artifact_version_id,
                    "requested_by": command.requested_by,
                    "payload_summary": self._json(command.payload_summary),
                    "expires_at": command.expires_at,
                    "interrupt_id": command.interrupt_id,
                    "resume_version": command.resume_version,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            self._insert_audit(
                organization_id=command.organization_id,
                approval_id=approval_id,
                action="REQUESTED",
                actor_id=command.requested_by,
                status_from=None,
                status_to=ApprovalStatus.PENDING,
                details={
                    "artifact_version_id": str(command.artifact_version_id),
                    "subject_version_ref": f"artifact:v{artifact['version_number']}",
                },
                now=now,
            )
            self._insert_outbox(
                organization_id=command.organization_id,
                event_type="approval.requested",
                approval_id=approval_id,
                payload={
                    "approval_id": str(approval_id),
                    "project_id": str(command.project_id),
                    "approval_type": ApprovalType.ARTIFACT_VERSION.value,
                    "artifact_version_id": str(command.artifact_version_id),
                },
                now=now,
            )
        return self.get(command.organization_id, approval_id, command.requested_by)

    def get(
        self, organization_id: UUID, approval_id: UUID, actor_id: str
    ) -> ApprovalRecord:
        self._assert_org(organization_id)
        row = self.session.execute(
            text(
                "SELECT * FROM approval_requests WHERE id=:id AND organization_id=:organization_id"
            ),
            {"id": approval_id, "organization_id": organization_id},
        ).mappings().one_or_none()
        if row is None:
            raise ApprovalNotFound("APPROVAL_NOT_FOUND")
        self.require_project_access(
            organization_id=organization_id,
            project_id=row["project_id"],
            actor_id=actor_id,
        )
        return self._approval(row)

    def list_project(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        actor_id: str,
        status: ApprovalStatus | None = None,
        limit: int = 100,
    ) -> tuple[ApprovalRecord, ...]:
        self._assert_org(organization_id)
        self.require_project_access(
            organization_id=organization_id,
            project_id=project_id,
            actor_id=actor_id,
        )
        if limit < 1 or limit > 200:
            raise ValueError("APPROVAL_LIST_LIMIT_OUT_OF_RANGE")
        rows = self.session.execute(
            text(
                """
                SELECT * FROM approval_requests
                WHERE organization_id=:organization_id
                  AND project_id=:project_id
                  AND (:status IS NULL OR status=:status)
                ORDER BY created_at DESC, id DESC
                LIMIT :limit
                """
            ),
            {
                "organization_id": organization_id,
                "project_id": project_id,
                "status": status.value if status is not None else None,
                "limit": limit,
            },
        ).mappings().all()
        return tuple(self._approval(row) for row in rows)

    def decide(
        self, command: ApprovalDecisionCommand
    ) -> tuple[ApprovalRecord, ApprovalDecision, tuple[ApprovalEffect, ...]]:
        self._assert_org(command.organization_id)
        existing_decision = self.session.execute(
            text(
                """
                SELECT * FROM approval_decisions
                WHERE organization_id=:organization_id AND operation_id=:operation_id
                """
            ),
            {
                "organization_id": command.organization_id,
                "operation_id": command.operation_id,
            },
        ).mappings().one_or_none()
        if existing_decision is not None:
            if existing_decision["approval_id"] != command.approval_id:
                raise ApprovalConflict("APPROVAL_DECISION_OPERATION_CONFLICT")
            approval = self.get(
                command.organization_id, command.approval_id, command.actor_id
            )
            return (
                approval,
                self._decision(existing_decision),
                self.list_effects(command.organization_id, command.approval_id),
            )

        stale_code: str | None = None
        decision_id = new_uuid7()
        with self._transaction():
            row = self._approval_for_update(
                command.organization_id, command.approval_id
            )
            self.require_project_access(
                organization_id=command.organization_id,
                project_id=row["project_id"],
                actor_id=command.actor_id,
            )
            required_permission = str(row["required_permission"])
            if required_permission not in command.actor_permissions:
                raise ApprovalForbidden("APPROVAL_PERMISSION_REQUIRED")
            if row["status"] != ApprovalStatus.PENDING.value:
                raise ApprovalConflict("APPROVAL_ALREADY_RESOLVED")

            if row["expires_at"] is not None and command.decided_at >= row["expires_at"]:
                self._transition_locked(
                    row,
                    status=ApprovalStatus.EXPIRED,
                    actor_id=None,
                    now=command.decided_at,
                    action="EXPIRED",
                    changes={},
                )
                stale_code = "APPROVAL_EXPIRED"
            else:
                stale_code = self._artifact_stale_code(row)
                if stale_code is not None:
                    self._transition_locked(
                        row,
                        status=ApprovalStatus.SUPERSEDED,
                        actor_id=None,
                        now=command.decided_at,
                        action="SUPERSEDED",
                        changes={},
                    )
                else:
                    target_status = ApprovalStatus(command.decision.value)
                    feedback = dict(command.feedback)
                    if command.decision != ApprovalDecisionKind.APPROVED and not (
                        command.reason or feedback
                    ):
                        raise ValueError(
                            "rejection/changes decision requires reason or feedback"
                        )
                    next_version = int(row["version"]) + 1
                    self.session.execute(
                        text(
                            """
                            INSERT INTO approval_decisions (
                                id, organization_id, approval_id, operation_id, decision,
                                actor_id, reason, feedback_json, approval_version, created_at
                            ) VALUES (
                                :id, :organization_id, :approval_id, :operation_id, :decision,
                                :actor_id, :reason, CAST(:feedback AS jsonb), :approval_version, :created_at
                            )
                            """
                        ),
                        {
                            "id": decision_id,
                            "organization_id": command.organization_id,
                            "approval_id": command.approval_id,
                            "operation_id": command.operation_id,
                            "decision": command.decision.value,
                            "actor_id": command.actor_id,
                            "reason": command.reason,
                            "feedback": self._json(feedback),
                            "approval_version": next_version,
                            "created_at": command.decided_at,
                        },
                    )
                    changes = (
                        {
                            "reason": command.reason,
                            "feedback": feedback,
                        }
                        if command.decision == ApprovalDecisionKind.CHANGES_REQUESTED
                        else {}
                    )
                    self._transition_locked(
                        row,
                        status=target_status,
                        actor_id=command.actor_id,
                        now=command.decided_at,
                        action="DECISION_RECORDED",
                        changes=changes,
                    )
                    self._create_effects_for_decision(
                        row=row,
                        decision=command.decision,
                        actor_id=command.actor_id,
                        reason=command.reason,
                        feedback=feedback,
                        now=command.decided_at,
                    )
                    self._insert_outbox(
                        organization_id=command.organization_id,
                        event_type="approval.decided",
                        approval_id=command.approval_id,
                        payload={
                            "approval_id": str(command.approval_id),
                            "project_id": str(row["project_id"]),
                            "decision": command.decision.value,
                        },
                        now=command.decided_at,
                    )
        if stale_code is not None:
            raise ApprovalStale(stale_code)
        approval = self.get(
            command.organization_id, command.approval_id, command.actor_id
        )
        decision_row = self.session.execute(
            text(
                "SELECT * FROM approval_decisions WHERE id=:id AND organization_id=:organization_id"
            ),
            {"id": decision_id, "organization_id": command.organization_id},
        ).mappings().one()
        return (
            approval,
            self._decision(decision_row),
            self.list_effects(command.organization_id, command.approval_id),
        )

    def list_audit(
        self, *, organization_id: UUID, approval_id: UUID, actor_id: str
    ) -> tuple[ApprovalAuditEntry, ...]:
        approval = self.get(organization_id, approval_id, actor_id)
        rows = self.session.execute(
            text(
                """
                SELECT * FROM approval_audit_events
                WHERE organization_id=:organization_id AND approval_id=:approval_id
                ORDER BY created_at, id
                """
            ),
            {
                "organization_id": approval.organization_id,
                "approval_id": approval.id,
            },
        ).mappings().all()
        return tuple(self._audit(row) for row in rows)

    def list_effects(
        self, organization_id: UUID, approval_id: UUID
    ) -> tuple[ApprovalEffect, ...]:
        self._assert_org(organization_id)
        rows = self.session.execute(
            text(
                """
                SELECT * FROM approval_effects
                WHERE organization_id=:organization_id AND approval_id=:approval_id
                ORDER BY created_at, id
                """
            ),
            {"organization_id": organization_id, "approval_id": approval_id},
        ).mappings().all()
        return tuple(self._effect(row) for row in rows)

    def _artifact_snapshot(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        artifact_version_id: UUID,
        lock: bool,
    ) -> Mapping[str, Any]:
        suffix = " FOR UPDATE" if lock else ""
        row = self.session.execute(
            text(
                """
                SELECT av.id, av.artifact_id, av.version_number, av.status, av.content_hash
                FROM artifact_versions av
                JOIN artifacts a
                  ON a.id=av.artifact_id
                 AND a.organization_id=av.organization_id
                WHERE av.id=:artifact_version_id
                  AND av.organization_id=:organization_id
                  AND a.project_id=:project_id
                  AND a.deleted_at IS NULL
                """ + suffix
            ),
            {
                "artifact_version_id": artifact_version_id,
                "organization_id": organization_id,
                "project_id": project_id,
            },
        ).mappings().one_or_none()
        if row is None:
            raise ApprovalNotFound("ARTIFACT_VERSION_NOT_FOUND")
        return row

    def _artifact_stale_code(self, approval: Mapping[str, Any]) -> str | None:
        if approval["approval_type"] != ApprovalType.ARTIFACT_VERSION.value:
            return None
        row = self._artifact_snapshot(
            organization_id=approval["organization_id"],
            project_id=approval["project_id"],
            artifact_version_id=approval["artifact_version_id"],
            lock=True,
        )
        if row["content_hash"] != approval["subject_snapshot_hash"]:
            return "APPROVAL_SUBJECT_SNAPSHOT_CHANGED"
        if row["status"] != "READY":
            return "APPROVAL_SUBJECT_STATE_CHANGED"
        return None

    def _validate_runtime_links(self, command: ArtifactApprovalRequest) -> None:
        if command.interrupt_id is not None and command.agent_run_id is None:
            raise ValueError("approval interrupt requires agent_run_id")
        if command.agent_run_id is not None:
            exists = self.session.execute(
                text(
                    """
                    SELECT 1 FROM agent_runs
                    WHERE id=:id AND organization_id=:organization_id AND project_id=:project_id
                    """
                ),
                {
                    "id": command.agent_run_id,
                    "organization_id": command.organization_id,
                    "project_id": command.project_id,
                },
            ).scalar_one_or_none()
            if exists is None:
                raise ApprovalNotFound("AGENT_RUN_NOT_FOUND")
        if command.task_id is not None:
            exists = self.session.execute(
                text(
                    """
                    SELECT 1 FROM tasks
                    WHERE id=:id AND organization_id=:organization_id AND project_id=:project_id
                    """
                ),
                {
                    "id": command.task_id,
                    "organization_id": command.organization_id,
                    "project_id": command.project_id,
                },
            ).scalar_one_or_none()
            if exists is None:
                raise ApprovalNotFound("TASK_NOT_FOUND")

    def _get_by_request_operation(
        self, organization_id: UUID, operation_id: UUID
    ) -> ApprovalRecord | None:
        row = self.session.execute(
            text(
                """
                SELECT * FROM approval_requests
                WHERE organization_id=:organization_id AND request_operation_id=:operation_id
                """
            ),
            {"organization_id": organization_id, "operation_id": operation_id},
        ).mappings().one_or_none()
        return self._approval(row) if row is not None else None

    def _approval_for_update(
        self, organization_id: UUID, approval_id: UUID
    ) -> Mapping[str, Any]:
        row = self.session.execute(
            text(
                """
                SELECT * FROM approval_requests
                WHERE id=:id AND organization_id=:organization_id
                FOR UPDATE
                """
            ),
            {"id": approval_id, "organization_id": organization_id},
        ).mappings().one_or_none()
        if row is None:
            raise ApprovalNotFound("APPROVAL_NOT_FOUND")
        return row

    def _transition_locked(
        self,
        row: Mapping[str, Any],
        *,
        status: ApprovalStatus,
        actor_id: str | None,
        now: datetime,
        action: str,
        changes: dict[str, Any],
    ) -> None:
        next_version = int(row["version"]) + 1
        self.session.execute(
            text(
                """
                UPDATE approval_requests
                SET status=:status,
                    changes_requested_json=CAST(:changes AS jsonb),
                    resolved_at=:resolved_at,
                    updated_at=:updated_at,
                    version=:version
                WHERE id=:id AND organization_id=:organization_id
                """
            ),
            {
                "status": status.value,
                "changes": self._json(changes),
                "resolved_at": now,
                "updated_at": now,
                "version": next_version,
                "id": row["id"],
                "organization_id": row["organization_id"],
            },
        )
        self._insert_audit(
            organization_id=row["organization_id"],
            approval_id=row["id"],
            action=action,
            actor_id=actor_id,
            status_from=ApprovalStatus(str(row["status"])),
            status_to=status,
            details={},
            now=now,
        )

    def _create_effects_for_decision(
        self,
        *,
        row: Mapping[str, Any],
        decision: ApprovalDecisionKind,
        actor_id: str,
        reason: str | None,
        feedback: dict[str, Any],
        now: datetime,
    ) -> None:
        if (
            decision == ApprovalDecisionKind.APPROVED
            and row["approval_type"] == ApprovalType.ARTIFACT_VERSION.value
        ):
            self._insert_effect(
                row=row,
                effect_type=ApprovalEffectType.ARTIFACT_VERSION_APPROVE,
                payload={
                    "approval_id": str(row["id"]),
                    "artifact_version_id": str(row["artifact_version_id"]),
                    "approved_by_id": actor_id,
                },
                now=now,
            )
        if row["agent_run_id"] is not None and row["interrupt_id"] is not None:
            self._insert_effect(
                row=row,
                effect_type=ApprovalEffectType.AGENT_RUN_RESUME,
                payload={
                    "approval_id": str(row["id"]),
                    "agent_run_id": str(row["agent_run_id"]),
                    "interrupt_id": str(row["interrupt_id"]),
                    "resume_version": int(row["resume_version"]),
                    "decision": decision.value,
                    "reason": reason,
                    "feedback": feedback,
                },
                now=now,
            )

    def _insert_effect(
        self,
        *,
        row: Mapping[str, Any],
        effect_type: ApprovalEffectType,
        payload: dict[str, Any],
        now: datetime,
    ) -> None:
        effect_id = new_uuid7()
        self.session.execute(
            text(
                """
                INSERT INTO approval_effects (
                    id, organization_id, approval_id, effect_type, status,
                    operation_id, payload_json, attempt_count, created_at, updated_at
                ) VALUES (
                    :id, :organization_id, :approval_id, :effect_type, 'PENDING',
                    :operation_id, CAST(:payload AS jsonb), 0, :created_at, :updated_at
                )
                """
            ),
            {
                "id": effect_id,
                "organization_id": row["organization_id"],
                "approval_id": row["id"],
                "effect_type": effect_type.value,
                "operation_id": new_uuid7(),
                "payload": self._json(payload),
                "created_at": now,
                "updated_at": now,
            },
        )
        self._insert_outbox(
            organization_id=row["organization_id"],
            event_type="approval.effect.pending",
            approval_id=row["id"],
            payload={
                "approval_id": str(row["id"]),
                "effect_id": str(effect_id),
                "effect_type": effect_type.value,
            },
            now=now,
        )

    def _insert_audit(
        self,
        *,
        organization_id: UUID,
        approval_id: UUID,
        action: str,
        actor_id: str | None,
        status_from: ApprovalStatus | None,
        status_to: ApprovalStatus | None,
        details: dict[str, Any],
        now: datetime,
    ) -> None:
        self.session.execute(
            text(
                """
                INSERT INTO approval_audit_events (
                    id, organization_id, approval_id, action, actor_id,
                    status_from, status_to, details_json, created_at
                ) VALUES (
                    :id, :organization_id, :approval_id, :action, :actor_id,
                    :status_from, :status_to, CAST(:details AS jsonb), :created_at
                )
                """
            ),
            {
                "id": new_uuid7(),
                "organization_id": organization_id,
                "approval_id": approval_id,
                "action": action,
                "actor_id": actor_id,
                "status_from": status_from.value if status_from is not None else None,
                "status_to": status_to.value if status_to is not None else None,
                "details": self._json(details),
                "created_at": now,
            },
        )

    def _insert_outbox(
        self,
        *,
        organization_id: UUID,
        event_type: str,
        approval_id: UUID,
        payload: dict[str, Any],
        now: datetime,
    ) -> None:
        self.session.execute(
            text(
                """
                INSERT INTO outbox_events (
                    id, organization_id, event_type, aggregate_type,
                    aggregate_id, payload_json, occurred_at, created_at
                ) VALUES (
                    :id, :organization_id, :event_type, 'approval',
                    :aggregate_id, CAST(:payload AS jsonb), :occurred_at, :created_at
                )
                """
            ),
            {
                "id": new_uuid7(),
                "organization_id": organization_id,
                "event_type": event_type,
                "aggregate_id": approval_id,
                "payload": self._json(payload),
                "occurred_at": now,
                "created_at": now,
            },
        )

    @staticmethod
    def _approval(row: Mapping[str, Any]) -> ApprovalRecord:
        return ApprovalRecord(
            id=row["id"],
            organization_id=row["organization_id"],
            project_id=row["project_id"],
            request_operation_id=row["request_operation_id"],
            agent_run_id=row["agent_run_id"],
            task_id=row["task_id"],
            approval_type=ApprovalType(str(row["approval_type"])),
            subject_type=str(row["subject_type"]),
            subject_id=row["subject_id"],
            subject_version_ref=str(row["subject_version_ref"]),
            subject_snapshot_hash=row["subject_snapshot_hash"],
            artifact_version_id=row["artifact_version_id"],
            status=ApprovalStatus(str(row["status"])),
            requested_by=str(row["requested_by"]),
            required_permission=str(row["required_permission"]),
            policy_mode=ApprovalPolicyMode(str(row["policy_mode"])),
            policy_version=int(row["policy_version"]),
            min_approvals=int(row["min_approvals"]),
            payload_summary=dict(row["payload_summary_json"] or {}),
            changes_requested=dict(row["changes_requested_json"] or {}),
            expires_at=row["expires_at"],
            resolved_at=row["resolved_at"],
            superseded_by_id=row["superseded_by_id"],
            interrupt_id=row["interrupt_id"],
            resume_version=row["resume_version"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            version=int(row["version"]),
        )

    @staticmethod
    def _decision(row: Mapping[str, Any]) -> ApprovalDecision:
        return ApprovalDecision(
            id=row["id"],
            organization_id=row["organization_id"],
            approval_id=row["approval_id"],
            operation_id=row["operation_id"],
            decision=ApprovalDecisionKind(str(row["decision"])),
            actor_id=str(row["actor_id"]),
            reason=row["reason"],
            feedback=dict(row["feedback_json"] or {}),
            approval_version=int(row["approval_version"]),
            created_at=row["created_at"],
        )

    @staticmethod
    def _audit(row: Mapping[str, Any]) -> ApprovalAuditEntry:
        return ApprovalAuditEntry(
            id=row["id"],
            organization_id=row["organization_id"],
            approval_id=row["approval_id"],
            action=str(row["action"]),
            actor_id=row["actor_id"],
            status_from=(ApprovalStatus(str(row["status_from"])) if row["status_from"] else None),
            status_to=(ApprovalStatus(str(row["status_to"])) if row["status_to"] else None),
            details=dict(row["details_json"] or {}),
            created_at=row["created_at"],
        )

    @staticmethod
    def _effect(row: Mapping[str, Any]) -> ApprovalEffect:
        return ApprovalEffect(
            id=row["id"],
            organization_id=row["organization_id"],
            approval_id=row["approval_id"],
            effect_type=ApprovalEffectType(str(row["effect_type"])),
            status=ApprovalEffectStatus(str(row["status"])),
            operation_id=row["operation_id"],
            payload=dict(row["payload_json"] or {}),
            attempt_count=int(row["attempt_count"]),
            last_error=row["last_error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=row["completed_at"],
        )

    @staticmethod
    def _json(value: dict[str, Any]) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
