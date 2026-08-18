from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from lumi_api.domain.ids import new_uuid7

from .contracts import (
    AuditExportRequest,
    AuditPage,
    AuditRecord,
    AuditResult,
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
    """Request-scoped NODE-65 repository.

    Transaction ownership intentionally belongs to the service factory. Repository methods
    never commit or rollback on their own, allowing a governance mutation and its mandatory
    audit event to succeed or fail as one unit of work.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def append_audit(self, event: AuditWrite) -> AuditRecord:
        event_id = new_uuid7()
        # Serialize the chain head per organization inside the caller transaction. Without
        # this fence two concurrent writers can observe the same previous_hash and fork.
        self.session.execute(
            text(
                "SELECT pg_advisory_xact_lock(hashtextextended(CAST(:scope AS text), 0))"
            ),
            {"scope": f"audit:{event.organization_id}"},
        )
        previous = self.session.execute(
            text(
                """
                SELECT event_hash
                FROM audit_events
                WHERE organization_id=:organization_id
                ORDER BY occurred_at DESC,id DESC
                LIMIT 1
                """
            ),
            {"organization_id": event.organization_id},
        ).scalar_one_or_none()
        previous_hash = str(previous) if previous is not None else None
        event_hash = self._event_hash(
            event_id=event_id,
            event=event,
            previous_hash=previous_hash,
        )
        actor = event.actor
        row = self.session.execute(
            text(
                """
                INSERT INTO audit_events(
                  id,organization_id,actor_type,actor_id,session_ref,api_token_ref,agent_run_ref,task_ref,
                  action,subject_type,subject_id,resource_version,result,reason_code,request_id,trace_id,
                  security_metadata_json,details_json,change_summary_json,retention_class,
                  retention_policy_version,occurred_at,previous_hash,event_hash,created_at
                ) VALUES(
                  :id,:organization_id,:actor_type,:actor_id,:session_ref,:api_token_ref,:agent_run_ref,:task_ref,
                  :action,:subject_type,:subject_id,:resource_version,:result,:reason_code,:request_id,:trace_id,
                  CAST(:security_metadata AS jsonb),CAST(:details AS jsonb),CAST(:change_summary AS jsonb),
                  :retention_class,:retention_policy_version,:occurred_at,:previous_hash,:event_hash,now()
                )
                RETURNING id,organization_id,actor_type,actor_id,action,subject_type,subject_id,
                          resource_version,result,reason_code,request_id,trace_id,change_summary_json,
                          retention_class,retention_policy_version,occurred_at,event_hash
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
                "security_metadata": self._json(event.security_metadata),
                "details": self._json(
                    {
                        **event.details,
                        "agent_version": actor.agent_version,
                        "human_initiator_user_id": (
                            str(actor.human_initiator_user_id)
                            if actor.human_initiator_user_id is not None
                            else None
                        ),
                    }
                ),
                "change_summary": self._json(
                    event.change_summary.model_dump(mode="json")
                ),
                "retention_class": event.retention_class.value,
                "retention_policy_version": event.retention_policy_version,
                "occurred_at": event.occurred_at,
                "previous_hash": previous_hash,
                "event_hash": event_hash,
            },
        ).mappings().one()
        return self._audit_record(row)

    def search_audit(self, query: AuditSearch) -> AuditPage:
        clauses = ["organization_id=:organization_id"]
        params: dict[str, Any] = {
            "organization_id": query.organization_id,
            "limit": query.limit + 1,
        }
        for column, value in (
            ("actor_id", query.actor_id),
            ("action", query.action),
            ("subject_type", query.resource_type),
            ("subject_id", query.resource_id),
            ("trace_id", query.trace_id),
        ):
            if value is not None:
                clauses.append(f"{column}=:{column}")
                params[column] = value
        if query.result is not None:
            clauses.append("result=:result")
            params["result"] = query.result.value
        if query.from_time is not None:
            clauses.append("occurred_at>=:from_time")
            params["from_time"] = query.from_time
        if query.to_time is not None:
            clauses.append("occurred_at<:to_time")
            params["to_time"] = query.to_time
        if query.cursor_occurred_at is not None and query.cursor_id is not None:
            clauses.append("(occurred_at,id)<(:cursor_occurred_at,:cursor_id)")
            params["cursor_occurred_at"] = query.cursor_occurred_at
            params["cursor_id"] = query.cursor_id
        rows = self.session.execute(
            text(
                f"""
                SELECT id,organization_id,actor_type,actor_id,action,subject_type,subject_id,
                       resource_version,result,reason_code,request_id,trace_id,change_summary_json,
                       retention_class,retention_policy_version,occurred_at,event_hash
                FROM audit_events
                WHERE {' AND '.join(clauses)}
                ORDER BY occurred_at DESC,id DESC
                LIMIT :limit
                """
            ),
            params,
        ).mappings().all()
        has_more = len(rows) > query.limit
        page_rows = rows[: query.limit]
        items = tuple(self._audit_record(row) for row in page_rows)
        if not has_more or not page_rows:
            return AuditPage(items=items)
        last = page_rows[-1]
        return AuditPage(
            items=items,
            next_cursor_occurred_at=last["occurred_at"],
            next_cursor_id=last["id"],
        )

    def active_retention_policy(
        self, retention_class: RetentionClass
    ) -> RetentionPolicy:
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
        return self._retention_policy(row)

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
                SELECT *
                FROM governance_legal_holds
                WHERE organization_id=:organization_id
                  AND released_at IS NULL
                  AND (
                    (scope_type=:scope_type AND scope_id=:scope_id)
                    OR (scope_type='ORGANIZATION' AND scope_id=:organization_scope_id)
                  )
                ORDER BY created_at,id
                """
            ),
            {
                "organization_id": organization_id,
                "scope_type": scope_type,
                "scope_id": scope_id,
                "organization_scope_id": str(organization_id),
            },
        ).mappings().all()
        return tuple(self._legal_hold(row) for row in rows)

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
        if scope_type not in {
            "ORGANIZATION",
            "USER",
            "PROJECT",
            "ASSET",
            "ARTIFACT",
            "AUDIT",
        }:
            raise ValueError("GOVERNANCE_LEGAL_HOLD_SCOPE_INVALID")
        row = self.session.execute(
            text(
                """
                INSERT INTO governance_legal_holds(
                  id,organization_id,hold_key,scope_type,scope_id,reason,created_by_user_id,created_at
                ) VALUES(:id,:organization_id,:hold_key,:scope_type,:scope_id,:reason,:actor,now())
                RETURNING *
                """
            ),
            {
                "id": new_uuid7(),
                "organization_id": organization_id,
                "hold_key": hold_key,
                "scope_type": scope_type,
                "scope_id": scope_id,
                "reason": reason,
                "actor": actor_user_id,
            },
        ).mappings().one()
        return self._legal_hold(row)

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
                SET released_by_user_id=:actor,released_at=now(),release_reason=:reason
                WHERE id=:hold_id AND organization_id=:organization_id AND released_at IS NULL
                RETURNING *
                """
            ),
            {
                "actor": actor_user_id,
                "reason": reason,
                "hold_id": hold_id,
                "organization_id": organization_id,
            },
        ).mappings().one_or_none()
        if row is None:
            existing = self.session.execute(
                text(
                    "SELECT released_at FROM governance_legal_holds "
                    "WHERE id=:hold_id AND organization_id=:organization_id"
                ),
                {"hold_id": hold_id, "organization_id": organization_id},
            ).mappings().one_or_none()
            if existing is None:
                raise GovernanceNotFound("GOVERNANCE_LEGAL_HOLD_NOT_FOUND")
            raise GovernanceConflict("GOVERNANCE_LEGAL_HOLD_ALREADY_RELEASED")
        return self._legal_hold(row)

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
        blocked = bool(hold_blockers)
        row = self.session.execute(
            text(
                """
                INSERT INTO governance_deletion_requests(
                  id,organization_id,subject_type,subject_id,status,requested_by_user_id,reason,
                  scope_json,hold_blockers_json,object_gc_status,search_gc_status,requested_at,updated_at,version
                ) VALUES(
                  :id,:organization_id,:subject_type,:subject_id,:status,:actor,:reason,
                  CAST(:scope AS jsonb),CAST(:hold_blockers AS jsonb),:object_gc,:search_gc,now(),now(),1
                ) RETURNING *
                """
            ),
            {
                "id": new_uuid7(),
                "organization_id": organization_id,
                "subject_type": subject_type,
                "subject_id": subject_id,
                "status": "HOLD_BLOCKED" if blocked else "IDENTIFIED",
                "actor": actor_user_id,
                "reason": reason,
                "scope": self._json(
                    {"subject_type": subject_type, "subject_id": subject_id}
                ),
                "hold_blockers": self._json(
                    [str(item) for item in hold_blockers]
                ),
                "object_gc": "BLOCKED" if blocked else "PENDING",
                "search_gc": "BLOCKED" if blocked else "PENDING",
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
            require_no_recorded_holds=True,
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
                ) VALUES(:id,:organization_id,:actor,:format,CAST(:filters AS jsonb),'PENDING',now())
                """
            ),
            {
                "id": export_id,
                "organization_id": organization_id,
                "actor": actor_user_id,
                "format": request.export_format,
                "filters": self._json(request.filters),
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
        require_no_recorded_holds: bool = False,
    ) -> DeletionRequest:
        state_params = {f"from_state_{index}": value for index, value in enumerate(from_states)}
        state_clause = ",".join(f":from_state_{index}" for index in range(len(from_states)))
        hold_clause = (
            " AND jsonb_array_length(hold_blockers_json)=0"
            if require_no_recorded_holds
            else ""
        )
        row = self.session.execute(
            text(
                f"""
                UPDATE governance_deletion_requests
                SET status=:status,object_gc_status=:object_gc_status,
                    search_gc_status=:search_gc_status,
                    completed_at=CASE WHEN :complete THEN now() ELSE completed_at END,
                    updated_at=now(),version=version+1
                WHERE id=:request_id AND status IN ({state_clause}){hold_clause}
                RETURNING *
                """
            ),
            {
                "request_id": request_id,
                "status": status,
                "object_gc_status": object_gc_status,
                "search_gc_status": search_gc_status,
                "complete": complete,
                **state_params,
            },
        ).mappings().one_or_none()
        if row is None:
            raise GovernanceConflict("GOVERNANCE_DELETION_STATE_CONFLICT")
        return self._deletion(row)

    @staticmethod
    def _event_hash(
        *, event_id: UUID, event: AuditWrite, previous_hash: str | None
    ) -> str:
        payload = {
            "id": str(event_id),
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
        canonical = json.dumps(
            payload,
            separators=(",", ":"),
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(
            value,
            separators=(",", ":"),
            sort_keys=True,
            ensure_ascii=False,
        )

    @staticmethod
    def _audit_record(row: Mapping[str, Any]) -> AuditRecord:
        return AuditRecord(
            id=row["id"],
            organization_id=row["organization_id"],
            actor_type=str(row["actor_type"]),
            actor_id=str(row["actor_id"]),
            action=str(row["action"]),
            resource_type=str(row["subject_type"]),
            resource_id=str(row["subject_id"]),
            resource_version=row["resource_version"],
            result=AuditResult(str(row["result"])),
            reason_code=row["reason_code"],
            request_id=row["request_id"],
            trace_id=row["trace_id"],
            safe_change_summary=dict(row["change_summary_json"] or {}),
            retention_class=RetentionClass(str(row["retention_class"])),
            retention_policy_version=str(row["retention_policy_version"]),
            occurred_at=row["occurred_at"],
            event_hash=str(row["event_hash"]),
        )

    @staticmethod
    def _retention_policy(row: Mapping[str, Any]) -> RetentionPolicy:
        return RetentionPolicy(
            id=row["id"],
            retention_class=RetentionClass(str(row["retention_class"])),
            policy_version=str(row["policy_version"]),
            retain_days=int(row["retain_days"]),
            active=bool(row["active"]),
            description=str(row["description"]),
            created_at=row["created_at"],
        )

    @staticmethod
    def _legal_hold(row: Mapping[str, Any]) -> LegalHold:
        return LegalHold(
            id=row["id"],
            organization_id=row["organization_id"],
            hold_key=str(row["hold_key"]),
            scope_type=str(row["scope_type"]),
            scope_id=str(row["scope_id"]),
            reason=str(row["reason"]),
            created_by_user_id=row["created_by_user_id"],
            created_at=row["created_at"],
            released_by_user_id=row["released_by_user_id"],
            released_at=row["released_at"],
            release_reason=row["release_reason"],
        )

    @staticmethod
    def _deletion(row: Mapping[str, Any]) -> DeletionRequest:
        blockers = tuple(
            UUID(str(item)) for item in (row["hold_blockers_json"] or [])
        )
        return DeletionRequest(
            id=row["id"],
            organization_id=row["organization_id"],
            subject_type=str(row["subject_type"]),
            subject_id=str(row["subject_id"]),
            status=DeletionStatus(str(row["status"])),
            requested_by_user_id=row["requested_by_user_id"],
            reason=str(row["reason"]),
            scope=dict(row["scope_json"] or {}),
            hold_blockers=blockers,
            object_gc_status=str(row["object_gc_status"]),
            search_gc_status=str(row["search_gc_status"]),
            requested_at=row["requested_at"],
            completed_at=row["completed_at"],
            updated_at=row["updated_at"],
            version=int(row["version"]),
        )
