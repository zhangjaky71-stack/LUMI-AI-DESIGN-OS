from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from lumi_api.auth import AccessPolicyService, OrganizationRole
from lumi_api.governance import (
    AuditActor,
    AuditActorType,
    AuditExportRequest,
    AuditPage,
    AuditRecord,
    AuditResult,
    AuditSearch,
    AuditWrite,
    DeletionRequest,
    DeletionStatus,
    GovernanceConflict,
    GovernanceForbidden,
    GovernanceService,
    GovernanceUnavailable,
    LegalHold,
    RetentionClass,
    RetentionPolicy,
    redact_audit_mapping,
)

ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 8, 18, 9, 0, tzinfo=UTC)


def _record(event: AuditWrite) -> AuditRecord:
    return AuditRecord(
        id=uuid4(),
        organization_id=event.organization_id,
        actor_type=event.actor.actor_type,
        actor_id=event.actor.actor_id,
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
        event_hash="0" * 64,
    )


class FakeRepository:
    def __init__(self) -> None:
        self.organization_id = uuid4()
        self.user_id = uuid4()
        self.events: list[AuditWrite] = []
        self.holds: list[LegalHold] = []
        self.deletions: dict[UUID, DeletionRequest] = {}
        self.export_ids: list[UUID] = []
        self.export_requests: list[AuditExportRequest] = []

    def append_audit(self, event: AuditWrite) -> AuditRecord:
        self.events.append(event)
        return _record(event)

    def search_audit(self, query: AuditSearch) -> AuditPage:
        del query
        return AuditPage(items=tuple(_record(event) for event in self.events))

    def active_retention_policy(
        self, retention_class: RetentionClass
    ) -> RetentionPolicy:
        return RetentionPolicy(
            id=uuid4(),
            retention_class=retention_class,
            policy_version="technical-baseline-2026-08",
            retain_days=30,
            active=True,
            description="test technical baseline",
            created_at=NOW,
        )

    def active_holds(
        self,
        *,
        organization_id: UUID,
        scope_type: str,
        scope_id: str,
    ) -> tuple[LegalHold, ...]:
        return tuple(
            hold
            for hold in self.holds
            if hold.organization_id == organization_id
            and hold.released_at is None
            and (
                (hold.scope_type == scope_type and hold.scope_id == scope_id)
                or (
                    hold.scope_type == "ORGANIZATION"
                    and hold.scope_id == str(organization_id)
                )
            )
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
    ) -> LegalHold:
        hold = LegalHold(
            id=uuid4(),
            organization_id=organization_id,
            hold_key=hold_key,
            scope_type=scope_type,
            scope_id=scope_id,
            reason=reason,
            created_by_user_id=actor_user_id,
            created_at=NOW,
        )
        self.holds.append(hold)
        return hold

    def release_legal_hold(
        self,
        *,
        organization_id: UUID,
        hold_id: UUID,
        reason: str,
        actor_user_id: UUID,
    ) -> LegalHold:
        for index, hold in enumerate(self.holds):
            if hold.id == hold_id and hold.organization_id == organization_id:
                released = hold.model_copy(
                    update={
                        "released_by_user_id": actor_user_id,
                        "released_at": NOW,
                        "release_reason": reason,
                    }
                )
                self.holds[index] = released
                return released
        raise AssertionError("hold missing")

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
        request_id = uuid4()
        blocked = bool(hold_blockers)
        request = DeletionRequest(
            id=request_id,
            organization_id=organization_id,
            subject_type=subject_type,
            subject_id=subject_id,
            status=(
                DeletionStatus.HOLD_BLOCKED
                if blocked
                else DeletionStatus.IDENTIFIED
            ),
            requested_by_user_id=actor_user_id,
            reason=reason,
            scope={"subject_type": subject_type, "subject_id": subject_id},
            hold_blockers=hold_blockers,
            object_gc_status="BLOCKED" if blocked else "PENDING",
            search_gc_status="BLOCKED" if blocked else "PENDING",
            requested_at=NOW,
            updated_at=NOW,
            version=1,
        )
        self.deletions[request_id] = request
        return request

    def mark_deletion_deactivated(self, request_id: UUID) -> DeletionRequest:
        request = self.deletions[request_id].model_copy(
            update={
                "status": DeletionStatus.DEACTIVATED,
                "version": self.deletions[request_id].version + 1,
            }
        )
        self.deletions[request_id] = request
        return request

    def mark_deletion_erasing(self, request_id: UUID) -> DeletionRequest:
        request = self.deletions[request_id].model_copy(
            update={
                "status": DeletionStatus.ERASING,
                "object_gc_status": "RUNNING",
                "search_gc_status": "RUNNING",
                "version": self.deletions[request_id].version + 1,
            }
        )
        self.deletions[request_id] = request
        return request

    def mark_deletion_completed(self, request_id: UUID) -> DeletionRequest:
        request = self.deletions[request_id].model_copy(
            update={
                "status": DeletionStatus.COMPLETED,
                "object_gc_status": "COMPLETED",
                "search_gc_status": "COMPLETED",
                "completed_at": NOW,
                "version": self.deletions[request_id].version + 1,
            }
        )
        self.deletions[request_id] = request
        return request

    def mark_deletion_failed(self, request_id: UUID) -> DeletionRequest:
        request = self.deletions[request_id].model_copy(
            update={
                "status": DeletionStatus.FAILED,
                "object_gc_status": "FAILED",
                "search_gc_status": "FAILED",
                "version": self.deletions[request_id].version + 1,
            }
        )
        self.deletions[request_id] = request
        return request

    def create_audit_export(
        self,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        request: AuditExportRequest,
    ) -> UUID:
        del organization_id, actor_user_id
        export_id = uuid4()
        self.export_ids.append(export_id)
        self.export_requests.append(request)
        return export_id


class DeactivationPort:
    def __init__(self) -> None:
        self.deactivated: list[UUID] = []

    def deactivate_subject(self, request: DeletionRequest) -> None:
        self.deactivated.append(request.id)


class ObjectPort:
    def __init__(self) -> None:
        self.deleted: list[UUID] = []

    def delete_subject_objects(self, request: DeletionRequest) -> None:
        self.deleted.append(request.id)


class SearchPort:
    def __init__(self) -> None:
        self.deleted: list[UUID] = []

    def delete_subject_search_refs(self, request: DeletionRequest) -> None:
        self.deleted.append(request.id)


class ExportPort:
    def __init__(self) -> None:
        self.scheduled: list[UUID] = []

    def schedule(self, export_id: UUID) -> None:
        self.scheduled.append(export_id)


def test_redaction_removes_secrets_and_hashes_content() -> None:
    sanitized = redact_audit_mapping(
        {
            "password": "secret-password",
            "Authorization": "Bearer raw-token",
            "api_key": "sk-live-secret",
            "prompt": "private customer prompt",
            "download_url": "https://storage.example/a.png?X-Amz-Signature=secret&x=1",
            "nested": {"session_secret": "session-raw"},
        }
    )
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["Authorization"] == "[REDACTED]"
    assert sanitized["api_key"] == "[REDACTED]"
    assert str(sanitized["prompt"]).startswith("sha256:")
    assert sanitized["download_url"] == "https://storage.example/a.png"
    assert sanitized["nested"]["session_secret"] == "[REDACTED]"
    rendered = repr(sanitized)
    assert "raw-token" not in rendered
    assert "sk-live-secret" not in rendered
    assert "private customer prompt" not in rendered


def test_agent_actor_requires_run_version_and_human_initiator() -> None:
    with pytest.raises(ValueError, match="AGENT_AUDIT_REQUIRES_RUN"):
        AuditActor(actor_type=AuditActorType.AGENT, actor_id="designer-agent")
    with pytest.raises(ValueError, match="SYSTEM_IDENTITY_FORBIDDEN"):
        AuditActor(
            actor_type=AuditActorType.AGENT,
            actor_id="system",
            agent_run_ref=uuid4(),
            agent_version="v1",
            human_initiator_user_id=uuid4(),
        )
    actor = AuditActor(
        actor_type=AuditActorType.AGENT,
        actor_id="designer-agent",
        agent_run_ref=uuid4(),
        task_ref=uuid4(),
        agent_version="2026.08",
        human_initiator_user_id=uuid4(),
    )
    assert actor.agent_run_ref is not None


def test_record_redacts_before_repository_append() -> None:
    repo = FakeRepository()
    service = GovernanceService(repo)  # type: ignore[arg-type]
    service.record(
        AuditWrite(
            organization_id=repo.organization_id,
            actor=AuditActor(actor_type="USER", actor_id=str(repo.user_id)),
            action="asset.download_sensitive",
            resource_type="asset",
            resource_id=str(uuid4()),
            result=AuditResult.SUCCESS,
            security_metadata={"Authorization": "Bearer abc"},
            details={"prompt": "do not persist me", "password": "pw"},
            retention_class=RetentionClass.SECURITY_AUDIT,
            retention_policy_version="technical-baseline-2026-08",
            occurred_at=NOW,
        )
    )
    persisted = repo.events[-1]
    assert persisted.security_metadata["Authorization"] == "[REDACTED]"
    assert str(persisted.details["prompt"]).startswith("sha256:")
    assert persisted.details["password"] == "[REDACTED]"


def test_org_admin_can_read_but_cannot_manage_governance() -> None:
    policy = AccessPolicyService()
    admin = tuple(
        item.value
        for item in policy.permissions_for_roles((OrganizationRole.ADMIN,))
    )
    owner = tuple(
        item.value
        for item in policy.permissions_for_roles((OrganizationRole.OWNER,))
    )
    assert "admin.audit.read" in admin
    assert "governance.manage" not in admin
    assert "audit.export" not in admin
    assert "governance.manage" in owner
    assert "audit.export" in owner

    service = GovernanceService(FakeRepository())  # type: ignore[arg-type]
    with pytest.raises(GovernanceForbidden):
        service.create_legal_hold(
            organization_id=uuid4(),
            hold_key="case-001",
            scope_type="USER",
            scope_id=str(uuid4()),
            reason="Legal preservation request",
            actor_user_id=uuid4(),
            permissions=admin,
        )


def test_legal_hold_marks_retention_candidate_and_blocks_deletion() -> None:
    repo = FakeRepository()
    service = GovernanceService(repo)  # type: ignore[arg-type]
    permissions = ("governance.manage", "admin.audit.read")
    subject_id = str(uuid4())
    hold = service.create_legal_hold(
        organization_id=repo.organization_id,
        hold_key="case-legal-001",
        scope_type="USER",
        scope_id=subject_id,
        reason="Preserve account for legal review",
        actor_user_id=repo.user_id,
        permissions=permissions,
    )
    candidate = service.retention_candidate(
        organization_id=repo.organization_id,
        retention_class=RetentionClass.CONTENT,
        resource_type="USER",
        resource_id=subject_id,
        occurred_at=NOW,
    )
    assert candidate.held is True
    assert candidate.hold_ids == (hold.id,)

    deletion = service.request_deletion(
        organization_id=repo.organization_id,
        subject_type="USER",
        subject_id=subject_id,
        reason="Customer requested account deletion",
        actor_user_id=repo.user_id,
        permissions=permissions,
    )
    assert deletion.status is DeletionStatus.HOLD_BLOCKED
    with pytest.raises(GovernanceConflict, match="LEGAL_HOLD_BLOCKS_DELETION"):
        service.execute_deletion(
            deletion,
            actor_user_id=repo.user_id,
            permissions=permissions,
        )


def test_hold_added_after_deletion_request_still_blocks_execution() -> None:
    repo = FakeRepository()
    permissions = ("governance.manage",)
    service = GovernanceService(
        repo,  # type: ignore[arg-type]
        subject_deactivation_port=DeactivationPort(),
        object_deletion_port=ObjectPort(),
        search_deletion_port=SearchPort(),
    )
    subject_id = str(uuid4())
    deletion = service.request_deletion(
        organization_id=repo.organization_id,
        subject_type="USER",
        subject_id=subject_id,
        reason="Customer requested account deletion",
        actor_user_id=repo.user_id,
        permissions=permissions,
    )
    assert deletion.hold_blockers == ()
    service.create_legal_hold(
        organization_id=repo.organization_id,
        hold_key="case-after-request",
        scope_type="USER",
        scope_id=subject_id,
        reason="New legal preservation requirement",
        actor_user_id=repo.user_id,
        permissions=permissions,
    )
    with pytest.raises(GovernanceConflict, match="LEGAL_HOLD_BLOCKS_DELETION"):
        service.execute_deletion(
            deletion,
            actor_user_id=repo.user_id,
            permissions=permissions,
        )


def test_deletion_requires_deactivation_object_and_search_propagation() -> None:
    repo = FakeRepository()
    permissions = ("governance.manage",)
    deletion = GovernanceService(repo).request_deletion(  # type: ignore[arg-type]
        organization_id=repo.organization_id,
        subject_type="USER",
        subject_id=str(uuid4()),
        reason="Customer requested account deletion",
        actor_user_id=repo.user_id,
        permissions=permissions,
    )
    with pytest.raises(GovernanceUnavailable, match="DELETION_PORTS_NOT_COMPOSED"):
        GovernanceService(repo).execute_deletion(  # type: ignore[arg-type]
            deletion,
            actor_user_id=repo.user_id,
            permissions=permissions,
        )

    deactivation = DeactivationPort()
    objects = ObjectPort()
    search = SearchPort()
    service = GovernanceService(  # type: ignore[arg-type]
        repo,
        subject_deactivation_port=deactivation,
        object_deletion_port=objects,
        search_deletion_port=search,
    )
    completed = service.execute_deletion(
        deletion,
        actor_user_id=repo.user_id,
        permissions=permissions,
    )
    assert completed.status is DeletionStatus.COMPLETED
    assert deactivation.deactivated == [deletion.id]
    assert objects.deleted == [deletion.id]
    assert search.deleted == [deletion.id]
    assert repo.events[-1].details["deactivation"] == "DEACTIVATED"
    assert repo.events[-1].details["object_gc"] == "COMPLETED"
    assert repo.events[-1].details["search_gc"] == "COMPLETED"


def test_audit_export_fails_closed_before_creating_orphan_and_redacts_filters() -> None:
    repo = FakeRepository()
    request = AuditExportRequest(
        export_format="JSON",
        filters={"Authorization": "Bearer raw", "prompt": "private query"},
    )
    with pytest.raises(GovernanceUnavailable, match="AUDIT_EXPORT_PORT_NOT_COMPOSED"):
        GovernanceService(repo).request_audit_export(  # type: ignore[arg-type]
            organization_id=repo.organization_id,
            actor_user_id=repo.user_id,
            request=request,
            permissions=("audit.export",),
        )
    assert repo.export_ids == []

    port = ExportPort()
    service = GovernanceService(  # type: ignore[arg-type]
        repo,
        audit_export_port=port,
    )
    export_id = service.request_audit_export(
        organization_id=repo.organization_id,
        actor_user_id=repo.user_id,
        request=request,
        permissions=("audit.export",),
    )
    assert port.scheduled == [export_id]
    persisted = repo.export_requests[-1]
    assert persisted.filters["Authorization"] == "[REDACTED]"
    assert str(persisted.filters["prompt"]).startswith("sha256:")


def test_migration_repository_and_api_encode_governance_safety_contracts() -> None:
    migration = (
        ROOT / "apps/api/migrations/versions/20260818_0025_sql/up.sql"
    ).read_text(encoding="utf-8")
    repository = (
        ROOT / "apps/api/src/lumi_api/governance/repository.py"
    ).read_text(encoding="utf-8")
    app_source = (
        ROOT / "apps/api/src/lumi_api/api/v1/app.py"
    ).read_text(encoding="utf-8")
    routes = (
        ROOT / "apps/api/src/lumi_api/api/v1/governance_routes.py"
    ).read_text(encoding="utf-8")

    assert "trg_audit_events_immutable" in migration
    assert "BEFORE UPDATE OR DELETE ON audit_events" in migration
    assert "ck_audit_events_actor_type" in migration
    assert "ck_audit_events_event_hash" in migration
    assert "node65_legacy_actor_type" in migration
    assert "node65_legacy_event_hash" in migration
    for retention_class in RetentionClass:
        assert retention_class.value in migration
    assert "governance_legal_holds" in migration
    assert "governance_deletion_requests" in migration
    assert "governance_audit_exports" in migration
    assert "legal review required before jurisdictional launch" in migration

    assert "pg_advisory_xact_lock" in repository
    assert "previous_hash" in repository
    assert "NOT EXISTS" in repository and "governance_legal_holds" in repository
    assert "jsonb_array_length" in repository
    assert "app.include_router(governance_router" in app_source
    assert "dependencies=[Depends(enforce_api_auth)]" in app_source
    assert '"governance.manage"' not in routes
