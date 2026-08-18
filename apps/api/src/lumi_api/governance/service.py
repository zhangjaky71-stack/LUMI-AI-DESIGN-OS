from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from .contracts import (
    AuditActor,
    AuditExportRequest,
    AuditPage,
    AuditRecord,
    AuditSearch,
    AuditWrite,
    DeletionRequest,
    GovernanceConflict,
    GovernanceForbidden,
    GovernanceUnavailable,
    LegalHold,
    RetentionCandidate,
    RetentionClass,
    RetentionPolicy,
)
from .redaction import redact_audit_mapping


class GovernanceRepository(Protocol):
    def append_audit(self, event: AuditWrite) -> AuditRecord: ...

    def search_audit(self, query: AuditSearch) -> AuditPage: ...

    def active_retention_policy(self, retention_class: RetentionClass) -> RetentionPolicy: ...

    def active_holds(
        self,
        *,
        organization_id: UUID,
        scope_type: str,
        scope_id: str,
    ) -> tuple[LegalHold, ...]: ...

    def create_legal_hold(
        self,
        *,
        organization_id: UUID,
        hold_key: str,
        scope_type: str,
        scope_id: str,
        reason: str,
        actor_user_id: UUID,
    ) -> LegalHold: ...

    def release_legal_hold(
        self,
        *,
        organization_id: UUID,
        hold_id: UUID,
        reason: str,
        actor_user_id: UUID,
    ) -> LegalHold: ...

    def create_deletion_request(
        self,
        *,
        organization_id: UUID,
        subject_type: str,
        subject_id: str,
        reason: str,
        actor_user_id: UUID,
        hold_blockers: tuple[UUID, ...],
    ) -> DeletionRequest: ...

    def mark_deletion_erasing(self, request_id: UUID) -> DeletionRequest: ...

    def mark_deletion_completed(self, request_id: UUID) -> DeletionRequest: ...

    def mark_deletion_failed(self, request_id: UUID) -> DeletionRequest: ...

    def create_audit_export(
        self,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        request: AuditExportRequest,
    ) -> UUID: ...


class ObjectDeletionPort(Protocol):
    def delete_subject_objects(self, request: DeletionRequest) -> None: ...


class SearchDeletionPort(Protocol):
    def delete_subject_search_refs(self, request: DeletionRequest) -> None: ...


class AuditExportPort(Protocol):
    def schedule(self, export_id: UUID) -> None: ...


class GovernanceService:
    def __init__(
        self,
        repository: GovernanceRepository,
        *,
        object_deletion_port: ObjectDeletionPort | None = None,
        search_deletion_port: SearchDeletionPort | None = None,
        audit_export_port: AuditExportPort | None = None,
    ) -> None:
        self.repository = repository
        self.object_deletion_port = object_deletion_port
        self.search_deletion_port = search_deletion_port
        self.audit_export_port = audit_export_port

    @staticmethod
    def _require(permissions: tuple[str, ...], permission: str) -> None:
        if permission not in permissions:
            raise GovernanceForbidden("GOVERNANCE_PERMISSION_DENIED")

    def record(self, event: AuditWrite) -> AuditRecord:
        safe = event.model_copy(
            update={
                "security_metadata": redact_audit_mapping(event.security_metadata),
                "details": redact_audit_mapping(event.details),
            }
        )
        return self.repository.append_audit(safe)

    def search(
        self,
        query: AuditSearch,
        *,
        permissions: tuple[str, ...],
    ) -> AuditPage:
        self._require(permissions, "admin.audit.read")
        return self.repository.search_audit(query)

    def retention_candidate(
        self,
        *,
        organization_id: UUID,
        retention_class: RetentionClass,
        resource_type: str,
        resource_id: str,
        occurred_at: datetime,
    ) -> RetentionCandidate:
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValueError("RETENTION_TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
        policy = self.repository.active_retention_policy(retention_class)
        holds = self.repository.active_holds(
            organization_id=organization_id,
            scope_type=resource_type.upper(),
            scope_id=resource_id,
        )
        expires_at = occurred_at + timedelta(days=policy.retain_days)
        return RetentionCandidate(
            retention_class=retention_class,
            resource_type=resource_type,
            resource_id=resource_id,
            expires_at=expires_at,
            held=bool(holds),
            hold_ids=tuple(hold.id for hold in holds),
        )

    def create_legal_hold(
        self,
        *,
        organization_id: UUID,
        hold_key: str,
        scope_type: str,
        scope_id: str,
        reason: str,
        actor_user_id: UUID,
        permissions: tuple[str, ...],
    ) -> LegalHold:
        self._require(permissions, "governance.manage")
        clean_reason = self._reason(reason)
        hold = self.repository.create_legal_hold(
            organization_id=organization_id,
            hold_key=hold_key.strip(),
            scope_type=scope_type.strip().upper(),
            scope_id=scope_id.strip(),
            reason=clean_reason,
            actor_user_id=actor_user_id,
        )
        self.record(
            self._governance_audit(
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="governance.legal_hold.created",
                resource_type="legal_hold",
                resource_id=str(hold.id),
                details={"scope_type": hold.scope_type, "scope_id": hold.scope_id},
            )
        )
        return hold

    def release_legal_hold(
        self,
        *,
        organization_id: UUID,
        hold_id: UUID,
        reason: str,
        actor_user_id: UUID,
        permissions: tuple[str, ...],
    ) -> LegalHold:
        self._require(permissions, "governance.manage")
        hold = self.repository.release_legal_hold(
            organization_id=organization_id,
            hold_id=hold_id,
            reason=self._reason(reason),
            actor_user_id=actor_user_id,
        )
        self.record(
            self._governance_audit(
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="governance.legal_hold.released",
                resource_type="legal_hold",
                resource_id=str(hold.id),
                details={"scope_type": hold.scope_type, "scope_id": hold.scope_id},
            )
        )
        return hold

    def request_deletion(
        self,
        *,
        organization_id: UUID,
        subject_type: str,
        subject_id: str,
        reason: str,
        actor_user_id: UUID,
        permissions: tuple[str, ...],
    ) -> DeletionRequest:
        self._require(permissions, "governance.manage")
        normalized_type = subject_type.strip().upper()
        if normalized_type not in {"USER", "ORGANIZATION"}:
            raise ValueError("GOVERNANCE_DELETION_SUBJECT_INVALID")
        holds = self.repository.active_holds(
            organization_id=organization_id,
            scope_type=normalized_type,
            scope_id=subject_id.strip(),
        )
        request = self.repository.create_deletion_request(
            organization_id=organization_id,
            subject_type=normalized_type,
            subject_id=subject_id.strip(),
            reason=self._reason(reason),
            actor_user_id=actor_user_id,
            hold_blockers=tuple(hold.id for hold in holds),
        )
        self.record(
            self._governance_audit(
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="governance.deletion.requested",
                resource_type="deletion_request",
                resource_id=str(request.id),
                details={
                    "subject_type": normalized_type,
                    "subject_id": subject_id.strip(),
                    "hold_count": len(holds),
                },
            )
        )
        return request

    def execute_deletion(
        self,
        request: DeletionRequest,
        *,
        actor_user_id: UUID,
        permissions: tuple[str, ...],
    ) -> DeletionRequest:
        self._require(permissions, "governance.manage")
        if request.hold_blockers:
            raise GovernanceConflict("GOVERNANCE_LEGAL_HOLD_BLOCKS_DELETION")
        if self.object_deletion_port is None or self.search_deletion_port is None:
            raise GovernanceUnavailable("GOVERNANCE_DELETION_PORTS_NOT_COMPOSED")
        erasing = self.repository.mark_deletion_erasing(request.id)
        try:
            self.object_deletion_port.delete_subject_objects(erasing)
            self.search_deletion_port.delete_subject_search_refs(erasing)
            completed = self.repository.mark_deletion_completed(request.id)
        except Exception:
            self.repository.mark_deletion_failed(request.id)
            raise
        self.record(
            self._governance_audit(
                organization_id=request.organization_id,
                actor_user_id=actor_user_id,
                action="governance.deletion.completed",
                resource_type="deletion_request",
                resource_id=str(request.id),
                details={
                    "subject_type": request.subject_type,
                    "object_gc": "COMPLETED",
                    "search_gc": "COMPLETED",
                },
            )
        )
        return completed

    def request_audit_export(
        self,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        request: AuditExportRequest,
        permissions: tuple[str, ...],
    ) -> UUID:
        self._require(permissions, "audit.export")
        export_id = self.repository.create_audit_export(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            request=request,
        )
        self.record(
            self._governance_audit(
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="governance.audit_export.requested",
                resource_type="audit_export",
                resource_id=str(export_id),
                details={"format": request.export_format, "filters": request.filters},
                retention_class=RetentionClass.EXPORT,
            )
        )
        if self.audit_export_port is None:
            raise GovernanceUnavailable("GOVERNANCE_AUDIT_EXPORT_PORT_NOT_COMPOSED")
        self.audit_export_port.schedule(export_id)
        return export_id

    @staticmethod
    def _reason(reason: str) -> str:
        value = reason.strip()
        if len(value) < 8 or len(value) > 1000:
            raise ValueError("GOVERNANCE_REASON_INVALID")
        return value

    @staticmethod
    def _governance_audit(
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        action: str,
        resource_type: str,
        resource_id: str,
        details: dict[str, object],
        retention_class: RetentionClass = RetentionClass.SECURITY_AUDIT,
    ) -> AuditWrite:
        return AuditWrite(
            organization_id=organization_id,
            actor=AuditActor(actor_type="USER", actor_id=str(actor_user_id)),
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            result="SUCCESS",
            details=details,
            retention_class=retention_class,
            retention_policy_version="technical-baseline-2026-08",
            occurred_at=datetime.now(UTC),
        )
