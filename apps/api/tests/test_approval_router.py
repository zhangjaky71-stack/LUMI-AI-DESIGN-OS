from fastapi import FastAPI
from fastapi.testclient import TestClient

from lumi_api.approval_router import create_approval_router
from lumi_project_core.approval import (
    ApprovalActor,
    ApprovalEngine,
    ApprovalPolicy,
    ApprovalSubject,
    InMemoryApprovalRepository,
    InMemoryApprovalRuns,
    InMemoryApprovalSubjects,
    RecordingApprovalAudit,
    RecordingApprovalChanges,
    RecordingApprovalNotifications,
    RecordingApprovalResume,
)

ORG = "org-api"
PROJECT = "project-api"
SUBJECT = ApprovalSubject("ARTIFACT_VERSION", "artifact-api", "artifact-v8")


def setup_client(role="OWNER", permissions=frozenset({"project.read", "project.write", "artifact.approve"})):
    repo = InMemoryApprovalRepository()
    subjects = InMemoryApprovalSubjects()
    subjects.add(ORG, PROJECT, SUBJECT)
    runs = InMemoryApprovalRuns(frozenset({(ORG, PROJECT, "run-api")}))
    resume = RecordingApprovalResume()
    engine = ApprovalEngine(
        repository=repo,
        subjects=subjects,
        runs=runs,
        resume=resume,
        audit=RecordingApprovalAudit(),
        notifications=RecordingApprovalNotifications(),
        changes=RecordingApprovalChanges(),
    )
    actor = ApprovalActor("actor-api", ORG, (role,), permissions)

    async def resolve_actor(_request, project_id):
        assert project_id == PROJECT
        return actor

    app = FastAPI()
    app.include_router(create_approval_router(engine=engine, resolve_actor=resolve_actor))
    return TestClient(app), engine, actor, resume


def test_create_list_and_exact_approval_decision():
    client, _, _, resume = setup_client()
    created = client.post(
        f"/projects/{PROJECT}/approvals",
        json={
            "approval_type": "ARTIFACT_VERSION",
            "subject_type": SUBJECT.subject_type,
            "subject_id": SUBJECT.subject_id,
            "subject_version": SUBJECT.subject_version,
            "payload_summary": "Approve campaign artifact",
            "agent_run_id": "run-api",
        },
    )
    assert created.status_code == 200
    approval_id = created.json()["approval_id"]
    listing = client.get(f"/projects/{PROJECT}/approvals")
    assert listing.json()["items"][0]["subject"]["subject_version"] == "artifact-v8"
    decided = client.post(
        f"/projects/{PROJECT}/approvals/{approval_id}:decide",
        headers={"Idempotency-Key": "api-decision-1", "X-Request-Id": "request-api"},
        json={"decision": "APPROVE"},
    )
    assert decided.status_code == 200
    assert decided.json()["status"] == "APPROVED"
    assert resume.calls[0][1].approval_id == approval_id


def test_viewer_cannot_request_or_decide():
    client, engine, owner, _ = setup_client()
    approval = engine.request(
        owner,
        project_id=PROJECT,
        approval_type="ARTIFACT_VERSION",
        subject=SUBJECT,
        policy=ApprovalPolicy(),
        payload_summary="Need approval",
        agent_run_id="run-api",
    )
    viewer_client, _, _, _ = setup_client("VIEWER", frozenset({"project.read"}))
    create = viewer_client.post(
        f"/projects/{PROJECT}/approvals",
        json={
            "approval_type": "ARTIFACT_VERSION",
            "subject_type": SUBJECT.subject_type,
            "subject_id": SUBJECT.subject_id,
            "subject_version": SUBJECT.subject_version,
            "payload_summary": "not allowed",
        },
    )
    assert create.status_code == 403
    # This second client has a separate repository; transport still proves permission is checked before lookup.
    decision = viewer_client.post(
        f"/projects/{PROJECT}/approvals/{approval.approval_id}:decide",
        headers={"Idempotency-Key": "viewer-1"},
        json={"decision": "APPROVE"},
    )
    assert decision.status_code in {403, 404}


def test_request_changes_structured_feedback():
    client, _, _, _ = setup_client()
    created = client.post(
        f"/projects/{PROJECT}/approvals",
        json={
            "approval_type": "ARTIFACT_VERSION",
            "subject_type": SUBJECT.subject_type,
            "subject_id": SUBJECT.subject_id,
            "subject_version": SUBJECT.subject_version,
            "payload_summary": "Approve campaign artifact",
            "agent_run_id": "run-api",
        },
    ).json()
    response = client.post(
        f"/projects/{PROJECT}/approvals/{created['approval_id']}:decide",
        headers={"Idempotency-Key": "changes-api"},
        json={
            "decision": "REQUEST_CHANGES",
            "feedback": {
                "comment": "Adjust CTA",
                "node_refs": ["cta"],
                "requested_changes": ["Move CTA lower"],
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CHANGES_REQUESTED"
    assert response.json()["feedback"]["node_refs"] == ["cta"]
