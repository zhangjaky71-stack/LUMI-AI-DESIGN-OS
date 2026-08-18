from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from lumi_api.domain.ids import new_uuid7

from .contracts import (
    AuditExportRequest,
    AuditPage,
    AuditRecord,
    AuditSearch,
    AuditWrite,
    DeletionRequest,
    DeletionStatus,
    GovernanceConflict,
    GovernanceNotFound,
    LegalHold,
    RetentionClass,
    RetentionPolicy,
)


class PostgresGovernanceRepository:
    """Request-scoped repository. The owning factory commits or rolls back the unit of work."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def append_audit(self, event: AuditWrite) -> AuditRecord:
        self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:scope, 0))"),
            {"scope": f"audit:{event.organization_id}"},
        )
        previous_hash = self.session.execute(
            text(
                """
                SELECT event_hash
                FROM audit_events
                WHERE organization_id=:organization_id
                ORDER BY occurred_at DESC, id DESC
                LIMIT 1
                """
            ),
            {"organization_id": event.organization_id},
        ).scalar_one_or_none()
        event_id = new_uuid7()
        event_hash = self._event_hash(event, previous_hash)
        actor = event.actor
        self.session.execute(
            text(
                """
                INSERT INTO audit_events (
                  id, organization_id, actor_type, actor_id,
                  session_ref, api_token_ref, agent_run_ref, task_ref,
                  action, subject_type, subject_id, resource_version,
                  result, reason_code, request_id, trace_id,
                  security_metadata_json, details_json, change_summary_json,
                  retention_class, retention_policy_version,
                  previous_hash, event_hash, occurred_at, created_at
                ) VALUES (
                  :id, :organization_id, :actor_type, :actor_id,
                  :session_ref, :api_token_ref, :agent_run_ref, :task_ref,
                  :action, :subject_type, :subject_id, :resource_version,
                  :result, :reason_code, :request_id, :trace_id,
                  CAST(:security_metadata_json AS jsonb), CAST(:details_json AS jsonb),
                  CAST(:change_summary_json AS jsonb), :retention_class,
                  :retention_policy_version, :previous_hash, :event_hash,
                  :occurred_at, :occurred_at
                )
                """
            ),
            {
                "id": event_id,
                "organization_id": event.organization_id,
                "actor_type": actor.actor_type.value,
                "actor_id": actor.actor_id,
                "session_ref": actor.session_ref,
                "api_token_ref": actor.api_token_ref,
                "agent_run_ref": actor.agent_run_ref,
                "task_ref": actor.task_ref,
                "action": event.action,
                "subject_type": event.resource_type,
                "subject_id": event.resource_id,
                "resource_version": event.resource_version,
                "result": event.result.value,
                "reason_code": event.reason_code,
                "request_id": event.request_id,
                "trace_id": event.trace_id,
                "security_metadata_json": json.dumps(event.security_metadata, sort_keys=True),
                "details_json": json.dumps(
                    {
                        **event.details,
                        "agent_version": actor.agent_version,
                        "human_initiator_user_id": (
                            str(actor.human_initiator_user_id)
                            if actor.human_initiator_user_id
                            else None
                        ),
                    },
                    sort_keys=True,
                ),
                "change_summary_json": event.change_summary.model_dump_json(),
                "retention_class": event.retention_class.value,
                "retention_policy_version": event.retention_policy_version,
                "previous_hash": previous_hash,
                "event_hash": event_hash,
                "occurred_at": event.occurred_at,
            },
        )
        return AuditRecord(
            id=event_id,
            organization_id=event.organization_id,
            actor_type=actor.actor_type,
            actor_id=actor.actor_id,
            action=event.action,
            resource_type=event.resource_type,
            resource_id=event.resource_id,
            resource_version=event.resource_version,
            result=event.result,
            reason_code=event.reason_code,
            request_id=event.request_id,
            trace_id=event.trace_id,
            safe_change_summary=event.change_summary.model_dump(mode="json"),
            retention_class=event.retention_class,
            retention_policy_version=event.retention_policy_version,
            occurred_at=event.occurred_at,
            event_hash=event_hash,
        )

    def search_audit(self, query: AuditSearch) -> AuditPage:
        conditions = ["organization_id=:organization_id"]
        params: dict[str, Any] = {"organization_id": query.organization_id, "limit": query.limit + 1}
        fields = {
            "actor_id": query.actor_id,
            "action": query.action,
            "subject_type": query.resource_type,
            "subject_id": query.resource_id,
            "trace_id": query.trace_id,
        }
        for column, value in fields.items():
            if value is not None:
                conditions.append(f"{column}=:{column}")
                params[column] = value
        if query.result is not None:
            conditions.append("result=:result")
            params["result"] = query.result.value
        if query.from_time is not None:
            conditions.append("occurred_at>=:from_time")
            params["from_time"] = query.from_time
        if query.to_time is not None:
            conditions.append("occurred_at<:to_time")
            params["to_time"] = query.to_time
        if query.cursor_occurred_at is not None and query.cursor_id is not None:
            conditions.append("(occurred_at,id)<(:cursor_occurred_at,:cursor_id)")
            params["cursor_occurred_at"] = query.cursor_occurred_at
            params["cursor_id"] = query.cursor_id
        rows = self.session.execute(
            text(
                f"""
                SELECT id,organization_id,actor_type,actor_id,action,
                       subject_type,subject_id,resource_version,result,reason_code,
                       request_id,trace_id,change_summary_json,retention_class,
                       retention_policy_version,occurred_at,event_hash
                FROM audit_events
                WHERE {' AND '.join(conditions)}
                ORDER BY occurred_at DESC,id DESC
                LIMIT :limit
                """
            ),
            params,
        ).mappings().all()
        has_more = len(rows) > query.limit
        visible = rows[: query.limit]
        items = tuple(self._audit_record(row) for row in visible)
        tail = visible[-1] if has_more and visible else None
        return AuditPage(
            items=items,
            next_cursor_occurred_at=tail["occurred_at"] if tail else None,
            next_cursor_id=tail["id"] if tail else None,
        )

    def active_retention_policy(self, retention_class: RetentionClass) -> RetentionPolicy:
        row = self.session.execute(
            text(
                """
                SELECT id,retention_class,policy_version,retain_days,active,description,created_at
                FROM governance_retention_policies
                WHERE retention_class=:retention_class AND active=true
                """
            ),
            {"retention_class": retention_class.value},
        ).mappings().one_or_none()
        if row is None:
            raise GovernanceNotFound("GOVERNANCE_RETENTION_POLICY_NOT_FOUND")
        return RetentionPolicy(**row)

    def active_holds(
        self,
        *,
        organization_id: UUID,
        scope_type: str,
        scope_id: str,
    ) -> tuple[LegalHold, ...]:
        rows = self.session.execute(
            text(
                """
                SELECT id,organization_id,hold_key,scope_type,scope_id,reason,
                       created_by_user_id,created_at,released_by_user_id,released_at,release_reason
                FROM governance_legal_holds
                WHERE organization_id=:organization_id AND released_at IS NULL
                  AND ((scope_type=:scope_type AND scope_id=:scope_id)
                       OR (scope_type='ORGANIZATION' AND scope_id=:organization_scope))
                ORDER BY created_at,id
                """
            ),
            {
                "organization_id": organization_id,
                "scope_type": scope_type,
                "scope_id": scope_id,
                "organization_scope": str(organization_id),
            },
        ).mappings().all()
        return tuple(LegalHold(**row) for row in rows)

    def create_legal_hold(
        self,
        *,
        organization_id: UUID,
        hold_key: str,
        scope_type: str,
        scope_id: str,
        reason: str,
        actor_user_id: UUID,
    ) -> LegalHold:
        hold_id = new_uuid7()
        row = self.session.execute(
            text(
                """
                INSERT INTO governance_legal_holds(
                  id,organization_id,hold_key,scope_type,scope_id,reason,
                  created_by_user_id,created_at
                ) VALUES (
                  :id,:organization_id,:hold_key,:scope_type,:scope_id,:reason,
                  :actor_user_id,now()
                )
                RETURNING id,organization_id,hold_key,scope_type,scope_id,reason,
                          created_by_user_id,created_at,released_by_user_id,released_at,release_reason
                """
            ),
            {
                "id": hold_id,
                "organization_id": organization_id,
                "hold_key": hold_key,
                "scope_type": scope_type,
                "scope_id": scope_id,
                "reason": reason,
                "actor_user_id": actor_user_id,
            },
        ).mappings().one()
        return LegalHold(**row)

    def release_legal_hold(
        self,
        *,
        organization_id: UUID,
        hold_id: UUID,
        reason: str,
        actor_user_id: UUID,
    ) -> LegalHold:
        row = self.session.execute(
            text(
                """
                UPDATE governance_legal_holds
                SET released_by_user_id=:actor_user_id,released_at=now(),release_reason=:reason
                WHERE id=:hold_id AND organization_id=:organization_id AND released_at IS NULL
                RETURNING id,organization_id,hold_key,scope_type,scope_id,reason,
                          created_by_user_id,created_at,released_by_user_id,released_at,release_reason
                """
            ),
            {
                "actor_user_id": actor_user_id,
                "reason": reason,
                "hold_id": hold_id,
                "organization_id": organization_id,
            },
        ).mappings().one_or_none()
        if row is None:
            raise GovernanceConflict("GOVERNANCE_LEGAL_HOLD_NOT_ACTIVE")
        return LegalHold(**row)

    def create_deletion_request(
        self,
        *,
        organization_id: UUID,
        subject_type: str,
        subject_id: str,
        reason: str,
        actor_user_id: UUID,
        hold_blockers: tuple[UUID, ...],
    ) -> DeletionRequest:
        request_id = new_uuid7()
        blocked = bool(hold_blockers)
        status = DeletionStatus.HOLD_BLOCKED.value if blocked else DeletionStatus.IDENTIFIED.value
        gc_status = "BLOCKED" if blocked else "PENDING"
        row = self.session.execute(
            text(
                """
                INSERT INTO governance_deletion_requests(
                  id,organization_id,subject_type,subject_id,status,requested_by_user_id,
                  reason,scope_json,hold_blockers_json,object_gc_status,search_gc_status,
                  requested_at,updated_at,version
                ) VALUES (
                  :id,:organization_id,:subject_type,:subject_id,:status,:actor_user_id,
                  :reason,'{}'::jsonb,CAST(:hold_blockers AS jsonb),:gc_status,:gc_status,
                  now(),now(),1
                )
                RETURNING *
                """
            ),
            {
                "id": request_id,
                "organization_id": organization_id,
                "subject_type": subject_type,
                "subject_id": subject_id,
                "status": status,
                "actor_user_id": actor_user_id,
                "reason": reason,
                "hold_blockers": json.dumps([str(item) for item in hold_blockers]),
                "gc_status": gc_status,
            },
        ).mappings().one()
        return self._deletion(row)

    def mark_deletion_erasing(self, request_id: UUID) -> DeletionRequest:
        return self._transition_deletion(
            request_id,
            from_states=("IDENTIFIED", "DEACTIVATED"),
            status="ERASING",
            object_gc_status="RUNNING",
            search_gc_status="RUNNING",
        )

    def mark_deletion_completed(self, request_id: UUID) -> DeletionRequest:
        return self._transition_deletion(
            request_id,
            from_states=("ERASING",),
            status="COMPLETED",
            object_gc_status="COMPLETED",
            search_gc_status="COMPLETED",
            complete=True,
        )

    def mark_deletion_failed(self, request_id: UUID) -> DeletionRequest:
        return self._transition_deletion(
            request_id,
            from_states=("ERASING",),
            status="FAILED",
            object_gc_status="FAILED",
            search_gc_status="FAILED",
        )

    def create_audit_export(
        self,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        request: AuditExportRequest,
    ) -> UUID:
        export_id = new_uuid7()
        self.session.execute(
            text(
                """
                INSERT INTO governance_audit_exports(
                  id,organization_id,requested_by_user_id,export_format,filters_json,status,requested_at
                ) VALUES (
                  :id,:organization_id,:actor_user_id,:export_format,CAST(:filters AS jsonb),'PENDING',now()
                )
                """
            ),
            {
                "id": export_id,
                "organization_id": organization_id,
                "actor_user_id": actor_user_id,
                "export_format": request.export_format,
                "filters": json.dumps(request.filters, sort_keys=True),
            },
        )
        return export_id

    def _transition_deletion(
        self,
        request_id: UUID,
        *,
        from_states: tuple[str, ...],
        status: str,
        object_gc_status: str,
        search_gc_status: str,
        complete: bool = False,
    ) -> DeletionRequest:
        row = self.session.execute(
            text(
                """
                UPDATE governance_deletion_requests
                SET status=:status,object_gc_status=:object_gc_status,
                    search_gc_status=:search_gc_status,
                    completed_at=CASE WHEN :complete THEN now() ELSE completed_at END,
                    updated_at=now(),version=version+1
                WHERE id=:request_id AND status = ANY(:from_states)
                RETURNING *
                """
            ),
            {
                "request_id": request_id,
                "from_states": list(from_states),
                "status": status,
                "object_gc_status": object_gc_status,
                "search_gc_status": search_gc_status,
                "complete": complete,
            },
        ).mappings().one_or_none()
        if row is None:
            raise GovernanceConflict("GOVERNANCE_DELETION_STATE_CONFLICT")
        return self._deletion(row)

    @staticmethod
    def _event_hash(event: AuditWrite, previous_hash: str | None) -> str:
        payload = {
            "organization_id": str(event.organization_id),
            "actor": event.actor.model_dump(mode="json"),
            "action": event.action,
            "resource_type": event.resource_type,
            "resource_id": event.resource_id,
            "resource_version": event.resource_version,
            "result": event.result.value,
            "reason_code": event.reason_code,
            "request_id": event.request_id,
            "trace_id": event.trace_id,
            "security_metadata": event.security_metadata,
            "details": event.details,
            "change_summary": event.change_summary.model_dump(mode="json"),
            "retention_class": event.retention_class.value,
            "retention_policy_version": event.retention_policy_version,
            "occurred_at": event.occurred_at.isoformat(),
            "previous_hash": previous_hash,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _audit_record(row: Any) -> AuditRecord:
        return AuditRecord(
            id=row["id"],
            organization_id=row["organization_id"],
            actor_type=row["actor_type"],
            actor_id=row["actor_id"],
            action=row["action"],
            resource_type=row["subject_type"],
            resource_id=row["subject_id"],
            resource_version=row["resource_version"],
            result=row["result"],
            reason_code=row["reason_code"],
            request_id=row["request_id"],
            trace_id=row["trace_id"],
            safe_change_summary=row["change_summary_json"],
            retention_class=row["retention_class"],
            retention_policy_version=row["retention_policy_version"],
            occurred_at=row["occurred_at"],
            event_hash=row["event_hash"],
        )

    @staticmethod
    def _deletion(row: Any) -> DeletionRequest:
        return DeletionRequest(
            id=row["id"],
            organization_id=row["organization_id"],
            subject_type=row["subject_type"],
            subject_id=row["subject_id"],
            status=row["status"],
            requested_by_user_id=row["requested_by_user_id"],
            reason=row["reason"],
            scope=row["scope_json"],
            hold_blockers=tuple(UUID(item) for item in row["hold_blockers_json"]),
            object_gc_status=row["object_gc_status"],
            search_gc_status=row["search_gc_status"],
            requested_at=row["requested_at"],
            completed_at=row["completed_at"],
            updated_at=row["updated_at"],
            version=row["version"],
        )
