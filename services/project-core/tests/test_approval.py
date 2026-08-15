from datetime import UTC, datetime, timedelta

import pytest

from lumi_project_core.approval import (
    ApprovalActor,
    ApprovalEngine,
    ApprovalError,
    ApprovalFeedback,
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

ORG = "org-a"
PROJECT = "project-a"
SUBJECT = ApprovalSubject("ARTIFACT_VERSION", "artifact-a", "artifact-v3")


def setup_engine(*, permissions=frozenset({"artifact.approve"}), roles=("OWNER",)):
    repo = InMemoryApprovalRepository()
    subjects = InMemoryApprovalSubjects()
    subjects.add(ORG, PROJECT, SUBJECT)
    runs = InMemoryApprovalRuns(frozenset({(ORG, PROJECT, "run-1")}))
    resume = RecordingApprovalResume()
    audit = RecordingApprovalAudit()
    notifications = RecordingApprovalNotifications()
    changes = RecordingApprovalChanges()
    engine = ApprovalEngine(
        repository=repo,
        subjects=subjects,
        runs=runs,
        resume=resume,
        audit=audit,
        notifications=notifications,
        changes=changes,
    )
    actor = ApprovalActor("user-owner", ORG, roles, permissions)
    return engine, actor, repo, subjects, runs, resume, audit, notifications, changes


def request(engine, actor, **kwargs):
    return engine.request(
        actor,
        project_id=PROJECT,
        approval_type="ARTIFACT_VERSION",
        subject=SUBJECT,
        policy=kwargs.pop("policy", ApprovalPolicy()),
        payload_summary="Approve artifact v3",
        agent_run_id=kwargs.pop("agent_run_id", "run-1"),
        **kwargs,
    )


def test_approve_exact_version_and_resume_envelope():
    engine, actor, _, _, _, resume, audit, notifications, _ = setup_engine()
    approval = request(engine, actor)
    resolved = engine.decide(
        actor,
        project_id=PROJECT,
        approval_id=approval.approval_id,
        decision="APPROVE",
        idempotency_key="decision-1",
    )
    assert resolved.status == "APPROVED"
    assert resolved.subject.subject_version == "artifact-v3"
    assert resume.calls[0][1].subject_version == "artifact-v3"
    assert notifications.notifications[0].approval_id == approval.approval_id
    assert any(item.event_type == "APPROVAL_APPROVED" for item in audit.events)


def test_new_subject_version_supersedes_pending_without_drifting_subject():
    engine, actor, repo, subjects, *_ = setup_engine()
    v3 = request(engine, actor)
    v4_subject = ApprovalSubject("ARTIFACT_VERSION", "artifact-a", "artifact-v4")
    subjects.add(ORG, PROJECT, v4_subject)
    v4 = engine.request(
        actor,
        project_id=PROJECT,
        approval_type="ARTIFACT_VERSION",
        subject=v4_subject,
        policy=ApprovalPolicy(),
        payload_summary="Approve artifact v4",
        agent_run_id="run-1",
    )
    old = repo.get(ORG, PROJECT, v3.approval_id)
    assert old is not None and old.status == "SUPERSEDED"
    assert old.subject.subject_version == "artifact-v3"
    assert old.superseded_by == v4.approval_id


def test_unauthorized_viewer_cannot_decide():
    engine, owner, *_ = setup_engine()
    approval = request(engine, owner)
    viewer = ApprovalActor("viewer", ORG, ("VIEWER",), frozenset({"project.read"}))
    with pytest.raises(ApprovalError, match="APPROVAL_FORBIDDEN"):
        engine.decide(
            viewer,
            project_id=PROJECT,
            approval_id=approval.approval_id,
            decision="APPROVE",
            idempotency_key="viewer-no",
        )


def test_duplicate_decision_is_idempotent_by_key():
    engine, actor, *_ = setup_engine()
    approval = request(engine, actor)
    first = engine.decide(
        actor,
        project_id=PROJECT,
        approval_id=approval.approval_id,
        decision="APPROVE",
        idempotency_key="same-key",
    )
    second = engine.decide(
        actor,
        project_id=PROJECT,
        approval_id=approval.approval_id,
        decision="APPROVE",
        idempotency_key="same-key",
    )
    assert first == second
    with pytest.raises(ApprovalError, match="APPROVAL_STALE"):
        engine.decide(
            actor,
            project_id=PROJECT,
            approval_id=approval.approval_id,
            decision="APPROVE",
            idempotency_key="different-key",
        )


def test_request_changes_creates_change_task_and_resumes_graph():
    engine, actor, *rest = setup_engine()
    resume, changes = rest[3], rest[-1]
    approval = request(engine, actor)
    feedback = ApprovalFeedback(
        comment="Move the CTA and keep the logo lockup.",
        node_refs=("cta",),
        requested_changes=("Move CTA 24px lower",),
    )
    updated = engine.decide(
        actor,
        project_id=PROJECT,
        approval_id=approval.approval_id,
        decision="REQUEST_CHANGES",
        feedback=feedback,
        idempotency_key="changes-1",
    )
    assert updated.status == "CHANGES_REQUESTED"
    assert changes.calls[0][4].node_refs == ("cta",)
    assert resume.calls[0][1].feedback == feedback


def test_expiry_fails_closed():
    engine, actor, *_ = setup_engine()
    approval = request(engine, actor, expires_at=(datetime.now(UTC) + timedelta(milliseconds=1)).isoformat())
    expired = repo_get_after_expiry(engine, actor, approval.approval_id)
    assert expired.status == "EXPIRED"


def repo_get_after_expiry(engine, actor, approval_id):
    import time
    time.sleep(0.01)
    return engine.get(actor, PROJECT, approval_id)


def test_missing_exact_subject_is_stale():
    engine, actor, _, subjects, *_ = setup_engine()
    approval = request(engine, actor)
    subjects.subjects.clear()
    with pytest.raises(ApprovalError, match="APPROVAL_STALE"):
        engine.decide(
            actor,
            project_id=PROJECT,
            approval_id=approval.approval_id,
            decision="APPROVE",
            idempotency_key="stale-subject",
        )


def test_graph_restart_can_resume_from_durable_approval_id():
    engine, actor, repo, subjects, runs, _, audit, notifications, changes = setup_engine()
    approval = request(engine, actor)
    restarted_resume = RecordingApprovalResume()
    restarted = ApprovalEngine(
        repository=repo,
        subjects=subjects,
        runs=runs,
        resume=restarted_resume,
        audit=audit,
        notifications=notifications,
        changes=changes,
    )
    restarted.decide(
        actor,
        project_id=PROJECT,
        approval_id=approval.approval_id,
        decision="APPROVE",
        idempotency_key="restart-1",
    )
    assert restarted_resume.calls[0][0] == "run-1"
    assert restarted_resume.calls[0][1].approval_id == approval.approval_id


def test_multi_approver_min_n_and_role_sequence_fixture():
    engine, owner, *_ = setup_engine()
    min_policy = ApprovalPolicy(mode="MIN_N", min_approvals=2)
    approval = request(engine, owner, policy=min_policy, agent_run_id=None)
    first = engine.decide(
        owner, project_id=PROJECT, approval_id=approval.approval_id,
        decision="APPROVE", idempotency_key="min-1"
    )
    assert first.status == "PENDING"
    admin = ApprovalActor("admin", ORG, ("ADMIN",), frozenset({"artifact.approve"}))
    second = engine.decide(
        admin, project_id=PROJECT, approval_id=approval.approval_id,
        decision="APPROVE", idempotency_key="min-2"
    )
    assert second.status == "APPROVED"

    seq_subject = ApprovalSubject("CUSTOM_REVIEW", "campaign-a", "review-v1")
    engine._subjects.add(ORG, PROJECT, seq_subject)  # deterministic fixture port
    seq = engine.request(
        owner, project_id=PROJECT, approval_type="CUSTOM_REVIEW", subject=seq_subject,
        policy=ApprovalPolicy(mode="ROLE_BASED_SEQUENCE", required_permission="artifact.approve", sequence_roles=("EDITOR", "OWNER")),
        payload_summary="Sequential review", agent_run_id=None,
    )
    editor = ApprovalActor("editor", ORG, ("EDITOR",), frozenset({"artifact.approve"}))
    pending = engine.decide(editor, project_id=PROJECT, approval_id=seq.approval_id,
                            decision="APPROVE", idempotency_key="seq-1")
    assert pending.status == "PENDING"
    final = engine.decide(owner, project_id=PROJECT, approval_id=seq.approval_id,
                          decision="APPROVE", idempotency_key="seq-2")
    assert final.status == "APPROVED"
