from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from lumi_project_core.admin_console import AdminAuditEvent
from lumi_project_core.governance import (
    AuditChangeSummary,
    AuditQuery,
    GovernanceActor,
    GovernanceEngine,
    GovernanceError,
    GovernanceResourceRef,
    InMemoryAuditExportStorage,
    InMemoryGovernanceDataPort,
    InMemoryGovernanceRepository,
    Node64AdminAuditSink,
    sanitize_metadata,
)


def make_engine(resources: tuple[GovernanceResourceRef, ...] = ()):
    repository = InMemoryGovernanceRepository()
    data = InMemoryGovernanceDataPort(resources)
    storage = InMemoryAuditExportStorage()
    return GovernanceEngine(repository=repository, data=data, export_storage=storage), repository, data, storage


def org_actor(org: str = "org-a", permissions: frozenset[str] | None = None) -> GovernanceActor:
    return GovernanceActor(
        actor_id="user-a",
        actor_type="USER",
        organization_id=org,
        permissions=permissions
        or frozenset(
            {
                "audit.read",
                "audit.export",
                "governance.retention.read",
                "governance.deletion.manage",
                "governance.legal_hold.read",
            }
        ),
        session_ref="session-ref-1",
    )


def platform_actor(permissions: frozenset[str] | None = None) -> GovernanceActor:
    return GovernanceActor(
        actor_id="security-1",
        actor_type="PLATFORM_ADMIN",
        organization_id=None,
        permissions=permissions
        or frozenset(
            {
                "admin.audit.read",
                "audit.correct",
                "audit.export",
                "audit.export.execute",
                "governance.retention.read",
                "governance.retention.manage",
                "governance.legal_hold.read",
                "governance.legal_hold.manage",
                "governance.deletion.manage",
            }
        ),
    )


def old_resource(
    resource_type: str,
    resource_id: str,
    *,
    subject: str = "user-a",
    retention_class: str = "CONTENT",
    erasure_mode: str = "DELETE",
    object_ref: str | None = None,
    search_ref: str | None = None,
) -> GovernanceResourceRef:
    return GovernanceResourceRef(
        resource_type=resource_type,
        resource_id=resource_id,
        organization_id="org-a",
        retention_class=retention_class,  # type: ignore[arg-type]
        created_at=(datetime.now(UTC) - timedelta(days=5000)).isoformat(),
        subject_user_id=subject,
        erasure_mode=erasure_mode,  # type: ignore[arg-type]
        object_ref=object_ref,
        search_ref=search_ref,
    )


def test_audit_is_append_only_hash_chained_and_correction_adds_new_event() -> None:
    engine, repository, _, _ = make_engine()
    actor = platform_actor()
    first = engine.record_audit(
        actor,
        action="ADMIN_PROVIDER_DISABLED",
        resource_type="PROVIDER",
        resource_id="image-primary",
        result="SUCCESS",
        reason_code="INCIDENT",
        security_metadata={"ticket_ref": "INC-65"},
    )
    second = engine.record_audit(
        actor,
        action="ADMIN_QUEUE_REQUEUED",
        resource_type="QUEUE_ITEM",
        resource_id="queue-1",
        result="SUCCESS",
        reason_code="RECOVERY",
    )
    assert second.prev_hash == first.event_hash
    assert repository.verify_hash_chains() is True
    correction = engine.correct_audit(
        actor,
        event_id=first.event_id,
        reason_code="METADATA_CLARIFICATION",
        note="Correct support classification only",
    )
    assert correction.correction_of_event_id == first.event_id
    assert repository.get_audit(first.event_id) == first
    assert len(repository.audit_events) == 3
    with pytest.raises(GovernanceError, match="AUDIT_EVENT_IMMUTABLE"):
        repository.append_audit(first)


def test_redaction_never_persists_secret_values_prompt_or_signed_query() -> None:
    values = dict(
        sanitize_metadata(
            {
                "password": "super-secret",
                "Authorization": "Bearer abc.def.ghi",
                "raw_api_key": "sk-live-123",
                "session_secret": "cookie-secret",
                "card_number": "4242424242424242",
                "raw_prompt": "customer confidential prompt text",
                "ip_address": "203.0.113.55",
                "download_url": "https://storage.example.test/file.png?signature=secret&x=1",
                "request_id": "req-65",
            }
        )
    )
    for key in ("password", "Authorization", "raw_api_key", "session_secret", "card_number"):
        assert values[key] == "[REDACTED]"
    assert values["raw_prompt"].startswith("sha256:")
    assert "customer confidential" not in values["raw_prompt"]
    assert values["ip_address"].startswith("sha256:")
    assert "signature=secret" not in values["download_url"]
    assert values["request_id"] == "req-65"


def test_org_audit_is_tenant_scoped_and_platform_security_can_cross_org() -> None:
    engine, _, _, _ = make_engine()
    engine.record_audit(
        org_actor("org-a"),
        action="PROJECT_ARCHIVED",
        resource_type="PROJECT",
        resource_id="project-a",
        result="SUCCESS",
        reason_code="USER_REQUEST",
    )
    engine.record_audit(
        org_actor("org-b"),
        action="PROJECT_ARCHIVED",
        resource_type="PROJECT",
        resource_id="project-b",
        result="SUCCESS",
        reason_code="USER_REQUEST",
    )
    page = engine.search_audit(org_actor("org-a"), AuditQuery(limit=20))
    assert [item.organization_id for item in page.items] == ["org-a"]
    with pytest.raises(GovernanceError, match="AUDIT_TENANT_SCOPE_MISMATCH"):
        engine.search_audit(org_actor("org-a"), AuditQuery(organization_id="org-b"))
    platform = engine.search_audit(platform_actor(), AuditQuery(limit=20))
    assert {item.organization_id for item in platform.items} == {"org-a", "org-b"}


def test_cursor_pagination_is_stable_and_not_offset_based() -> None:
    engine, _, _, _ = make_engine()
    actor = org_actor()
    for index in range(5):
        engine.record_audit(
            actor,
            action="ASSET_DOWNLOADED_SENSITIVE",
            resource_type="ASSET",
            resource_id=f"asset-{index}",
            result="SUCCESS",
            reason_code="DOWNLOAD",
            occurred_at=f"2026-08-15T00:00:0{index}+00:00",
        )
    first = engine.search_audit(actor, AuditQuery(limit=2))
    assert len(first.items) == 2 and first.next_cursor
    second = engine.search_audit(actor, AuditQuery(limit=2, cursor=first.next_cursor))
    assert len(second.items) == 2
    assert {item.event_id for item in first.items}.isdisjoint(item.event_id for item in second.items)


def test_agent_actor_requires_version_run_task_and_human_initiator() -> None:
    with pytest.raises(GovernanceError, match="GOVERNANCE_AGENT_IDENTITY_INCOMPLETE"):
        GovernanceActor(
            actor_id="designer-agent",
            actor_type="AGENT",
            organization_id="org-a",
            permissions=frozenset(),
            actor_version="v7",
        )
    engine, _, _, _ = make_engine()
    agent = GovernanceActor(
        actor_id="designer-agent",
        actor_type="AGENT",
        organization_id="org-a",
        permissions=frozenset(),
        actor_version="v7",
        agent_run_id="run-65",
        task_id="task-65",
        human_initiator_id="user-a",
    )
    event = engine.record_audit(
        agent,
        action="TOOL_WRITE_EXTERNAL",
        resource_type="TOOL_CALL",
        resource_id="tool-call-65",
        resource_version="web.publish@2.1.0",
        result="SUCCESS",
        reason_code="APPROVED_WRITE",
        trace_id="trace-65",
        change_summary=AuditChangeSummary(version_refs=("web.publish@2.1.0",)),
    )
    assert event.actor_type == "AGENT"
    assert event.actor_version == "v7"
    assert event.agent_run_ref == "run-65"
    assert event.task_ref == "task-65"
    assert event.human_initiator_id == "user-a"


def test_node64_admin_sink_enters_canonical_pipeline_without_raw_reason() -> None:
    engine, repository, _, _ = make_engine()
    sink = Node64AdminAuditSink(engine, repository)
    sink.emit(
        AdminAuditEvent(
            event_id="legacy-admin-1",
            event_type="ADMIN_PII_REVEALED",
            actor_id="privacy-1",
            target_type="USER",
            target_id="user-a",
            reason="Customer gave private case details that must not be copied",
            ticket_ref="PRIV-65",
            created_at=datetime.now(UTC).isoformat(),
            safe_metadata=(("fields", "email,phone"), ("organization_id", "org-a")),
        )
    )
    event = repository.search_audit(AuditQuery(organization_id="org-a")).items[0]
    metadata = dict(event.security_metadata)
    assert event.action == "ADMIN_PII_REVEALED"
    assert metadata["reason_hash"].startswith("sha256:")
    assert "private case details" not in repr(event)
    recent = sink.recent()
    assert recent and recent[0].event_type == "ADMIN_PII_REVEALED"


def test_retention_policy_is_versioned_and_legal_hold_blocks_candidate() -> None:
    resource = old_resource("ARTIFACT", "artifact-a", retention_class="CONTENT")
    engine, repository, _, _ = make_engine((resource,))
    actor = platform_actor()
    policies = engine.list_retention_policies(actor)
    assert len({item.retention_class for item in policies}) == 7
    current = repository.current_retention_policy("CONTENT")
    updated = engine.publish_retention_policy(
        actor,
        retention_class="CONTENT",
        version=current.version + 1,
        retention_days=30,
        policy_note="Enterprise content policy v2",
    )
    assert updated.version == 2
    assert engine.retention_candidates(actor, organization_id="org-a")
    hold = engine.create_hold(
        actor,
        hold_type="LEGAL",
        organization_id="org-a",
        scope_type="RESOURCE",
        scope_id="ARTIFACT:artifact-a",
        reason_code="LITIGATION",
        ticket_ref="LEGAL-65",
    )
    assert engine.retention_candidates(actor, organization_id="org-a") == ()
    engine.release_hold(actor, hold_id=hold.hold_id, reason_code="MATTER_CLOSED", ticket_ref="LEGAL-65")
    assert engine.retention_candidates(actor, organization_id="org-a")


def test_legal_hold_blocks_deletion_then_delete_propagates_object_and_search_gc() -> None:
    resources = (
        old_resource(
            "ASSET",
            "asset-a",
            object_ref="object://org-a/asset-a",
            search_ref="vector://org-a/asset-a",
        ),
        old_resource("PROFILE", "profile-a", erasure_mode="ANONYMIZE"),
        old_resource("AUDIT_EVENT", "audit-retained", retention_class="SECURITY_AUDIT", erasure_mode="RETENTION_ONLY"),
    )
    engine, _, data, _ = make_engine(resources)
    actor = platform_actor()
    hold = engine.create_hold(
        actor,
        hold_type="LEGAL",
        organization_id="org-a",
        scope_type="USER",
        scope_id="user-a",
        reason_code="LEGAL_CASE",
        ticket_ref="LEGAL-66",
    )
    request = engine.request_deletion(
        actor, subject_user_id="user-a", organization_id="org-a", request_id="delete-65"
    )
    blocked = engine.execute_deletion(actor, request.request_id)
    assert blocked.status == "BLOCKED_HOLD"
    assert hold.hold_id in blocked.blocked_hold_ids
    assert data.erased == []
    engine.release_hold(actor, hold_id=hold.hold_id, reason_code="CASE_CLOSED", ticket_ref="LEGAL-66")
    completed = engine.execute_deletion(actor, request.request_id)
    assert completed.status == "COMPLETED"
    assert completed.deleted_count == 1
    assert completed.anonymized_count == 1
    assert completed.retained_count == 1
    assert ("user-a", "org-a") in data.deactivated
    assert "object://org-a/asset-a" in data.gc_objects
    assert "vector://org-a/asset-a" in data.removed_search_refs
    assert ("AUDIT_EVENT:audit-retained", "RETENTION_ONLY") not in data.erased


def test_audit_export_is_async_ready_only_and_download_refresh_does_not_rerender() -> None:
    engine, repository, _, storage = make_engine()
    org = org_actor(permissions=frozenset({"audit.read", "audit.export"}))
    engine.record_audit(
        org,
        action="ARTIFACT_APPROVED",
        resource_type="ARTIFACT_VERSION",
        resource_id="artifact-v4",
        result="SUCCESS",
        reason_code="APPROVED",
    )
    job = engine.create_export(org, export_format="JSON", query=AuditQuery(limit=50))
    assert job.status == "PENDING"
    with pytest.raises(GovernanceError, match="AUDIT_EXPORT_NOT_READY"):
        engine.get_download(org, job.job_id)
    worker = GovernanceActor(
        actor_id="audit-export-worker",
        actor_type="SERVICE",
        organization_id=None,
        permissions=frozenset({"audit.export.execute"}),
    )
    ready = engine.run_export(worker, job.job_id)
    assert ready.status == "READY"
    assert ready.object_ref and ready.checksum_sha256 and ready.size_bytes
    assert "signed_url" not in ready.__dataclass_fields__
    first = engine.get_download(org, job.job_id, ttl_seconds=300)
    second = engine.get_download(org, job.job_id, ttl_seconds=300)
    assert first.signed_url != second.signed_url
    assert engine.get_export(org, job.job_id).job_id == job.job_id
    assert len(storage.objects) == 1
    assert repository.get_export_job(job.job_id).status == "READY"  # type: ignore[union-attr]
