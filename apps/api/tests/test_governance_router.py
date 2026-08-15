from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from lumi_api.governance_router import create_governance_router
from lumi_project_core.governance import (
    AuditQuery,
    GovernanceActor,
    GovernanceEngine,
    GovernanceResourceRef,
    InMemoryAuditExportStorage,
    InMemoryGovernanceDataPort,
    InMemoryGovernanceRepository,
)


def make_client():
    resources = (
        GovernanceResourceRef(
            resource_type="ASSET",
            resource_id="asset-old",
            organization_id="org-a",
            retention_class="CONTENT",
            created_at=(datetime.now(UTC) - timedelta(days=5000)).isoformat(),
            subject_user_id="user-subject",
            object_ref="object://org-a/asset-old",
            search_ref="vector://org-a/asset-old",
        ),
    )
    repository = InMemoryGovernanceRepository()
    data = InMemoryGovernanceDataPort(resources)
    storage = InMemoryAuditExportStorage()
    engine = GovernanceEngine(repository=repository, data=data, export_storage=storage)

    async def resolve_actor(request: Request) -> GovernanceActor:
        mode = request.headers.get("x-test-principal", "org")
        if mode == "platform":
            return GovernanceActor(
                actor_id="security-1",
                actor_type="PLATFORM_ADMIN",
                organization_id=None,
                permissions=frozenset(
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
        if mode == "worker":
            return GovernanceActor(
                actor_id="audit-export-worker",
                actor_type="SERVICE",
                organization_id=None,
                permissions=frozenset({"audit.export.execute"}),
            )
        return GovernanceActor(
            actor_id="org-admin",
            actor_type="USER",
            organization_id="org-a",
            permissions=frozenset(
                {
                    "audit.read",
                    "audit.export",
                    "governance.retention.read",
                    "governance.legal_hold.read",
                }
            ),
            session_ref="session-ref-a",
        )

    app = FastAPI()
    app.include_router(create_governance_router(engine=engine, resolve_actor=resolve_actor))
    return TestClient(app), engine, repository, data, storage


def seed(engine: GovernanceEngine) -> None:
    actor = GovernanceActor(
        actor_id="user-a",
        actor_type="USER",
        organization_id="org-a",
        permissions=frozenset({"audit.read"}),
    )
    engine.record_audit(
        actor,
        action="ARTIFACT_APPROVED",
        resource_type="ARTIFACT_VERSION",
        resource_id="artifact-v4",
        result="SUCCESS",
        reason_code="APPROVED",
        trace_id="trace-65",
        security_metadata={"raw_prompt": "do not persist me", "request_id": "req-65"},
    )


def test_org_audit_search_returns_safe_scoped_projection() -> None:
    client, engine, _, _, _ = make_client()
    seed(engine)
    response = client.get("/governance/audit")
    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["organization_id"] == "org-a"
    assert body["items"][0]["action"] == "ARTIFACT_APPROVED"
    assert "do not persist me" not in response.text


def test_org_actor_cannot_cross_tenant_or_publish_retention() -> None:
    client, _, _, _, _ = make_client()
    denied = client.get("/governance/audit?organization_id=org-b")
    assert denied.status_code == 403
    policy = client.post(
        "/governance/retention/policies",
        json={
            "retention_class": "CONTENT",
            "version": 2,
            "retention_days": 30,
            "policy_note": "test",
        },
    )
    assert policy.status_code == 403


def test_platform_can_publish_retention_and_create_release_hold() -> None:
    client, _, _, _, _ = make_client()
    headers = {"x-test-principal": "platform"}
    policy = client.post(
        "/governance/retention/policies",
        headers=headers,
        json={
            "retention_class": "CONTENT",
            "version": 2,
            "retention_days": 30,
            "policy_note": "Enterprise content policy",
        },
    )
    assert policy.status_code == 200
    hold = client.post(
        "/governance/legal-holds",
        headers=headers,
        json={
            "hold_type": "LEGAL",
            "organization_id": "org-a",
            "scope_type": "USER",
            "scope_id": "user-subject",
            "reason_code": "LITIGATION",
            "ticket_ref": "LEGAL-65",
        },
    )
    assert hold.status_code == 200
    hold_id = hold.json()["hold_id"]
    released = client.post(
        f"/governance/legal-holds/{hold_id}:release",
        headers=headers,
        json={"reason_code": "MATTER_CLOSED", "ticket_ref": "LEGAL-65"},
    )
    assert released.status_code == 200


def test_deletion_requires_privileged_actor_and_propagates_gc() -> None:
    client, _, _, data, _ = make_client()
    denied = client.post(
        "/governance/deletions",
        json={"subject_user_id": "user-subject", "organization_id": "org-a"},
    )
    assert denied.status_code == 403
    headers = {"x-test-principal": "platform"}
    requested = client.post(
        "/governance/deletions",
        headers=headers,
        json={
            "subject_user_id": "user-subject",
            "organization_id": "org-a",
            "request_id": "delete-api-65",
        },
    )
    assert requested.status_code == 200
    executed = client.post(
        "/governance/deletions/delete-api-65:execute", headers=headers
    )
    assert executed.status_code == 200
    assert executed.json()["status"] == "COMPLETED"
    assert "object://org-a/asset-old" in data.gc_objects
    assert "vector://org-a/asset-old" in data.removed_search_refs


def test_audit_export_signed_url_appears_only_in_download_response() -> None:
    client, engine, repository, _, _ = make_client()
    seed(engine)
    job = client.post(
        "/governance/audit/exports",
        json={"export_format": "JSON", "action": "ARTIFACT_APPROVED"},
    )
    assert job.status_code == 200
    job_id = job.json()["job_id"]
    assert "signed_url" not in job.text
    before = client.post(f"/governance/audit/exports/{job_id}:download")
    assert before.status_code == 409
    run = client.post(
        f"/governance/internal/audit/exports/{job_id}:run",
        headers={"x-test-principal": "worker"},
    )
    assert run.status_code == 200 and run.json()["status"] == "READY"
    assert "signed_url" not in run.text
    stored = repository.get_export_job(job_id)
    assert stored is not None and not hasattr(stored, "signed_url")
    first = client.post(f"/governance/audit/exports/{job_id}:download")
    second = client.post(f"/governance/audit/exports/{job_id}:download")
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["signed_url"] != second.json()["signed_url"]


def test_correction_is_new_event_not_mutation() -> None:
    client, engine, repository, _, _ = make_client()
    seed(engine)
    source = repository.search_audit(AuditQuery(organization_id="org-a")).items[0]
    response = client.post(
        f"/governance/audit/{source.event_id}:correct",
        headers={"x-test-principal": "platform"},
        json={"reason_code": "CLASSIFICATION_FIX", "note": "metadata correction"},
    )
    assert response.status_code == 200
    assert response.json()["correction_of_event_id"] == source.event_id
    assert repository.get_audit(source.event_id) == source
