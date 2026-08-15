from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Literal, Protocol
from uuid import uuid4

ApprovalType = Literal[
    "CREATIVE_DIRECTION",
    "ARTIFACT_VERSION",
    "BRAND_RULE_SET",
    "BUDGET_INCREASE",
    "EXTERNAL_PUBLISH",
    "DESTRUCTIVE_ACTION",
    "CUSTOM_REVIEW",
]
ApprovalStatus = Literal[
    "PENDING",
    "APPROVED",
    "REJECTED",
    "CHANGES_REQUESTED",
    "EXPIRED",
    "CANCELLED",
    "SUPERSEDED",
]
ApprovalDecision = Literal["APPROVE", "REJECT", "REQUEST_CHANGES"]
ApprovalPolicyMode = Literal["ANY_ONE", "ALL", "MIN_N", "ROLE_BASED_SEQUENCE"]

TERMINAL_STATUSES: frozenset[str] = frozenset(
    {"APPROVED", "REJECTED", "CHANGES_REQUESTED", "EXPIRED", "CANCELLED", "SUPERSEDED"}
)
FLOATING_VERSIONS = frozenset({"latest", "head", "current"})


class ApprovalError(RuntimeError):
    def __init__(self, code: str, status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True, slots=True)
class ApprovalActor:
    actor_id: str
    organization_id: str
    roles: tuple[str, ...]
    permissions: frozenset[str]


@dataclass(frozen=True, slots=True)
class ApprovalSubject:
    subject_type: str
    subject_id: str
    subject_version: str

    def __post_init__(self) -> None:
        if not self.subject_type.strip() or not self.subject_id.strip():
            raise ApprovalError("APPROVAL_SUBJECT_REQUIRED")
        _require_exact_version(self.subject_version)


@dataclass(frozen=True, slots=True)
class ApprovalPolicy:
    mode: ApprovalPolicyMode = "ANY_ONE"
    version: int = 1
    required_permission: str = "artifact.approve"
    required_roles: tuple[str, ...] = ()
    min_approvals: int = 1
    sequence_roles: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ApprovalError("APPROVAL_POLICY_VERSION_INVALID")
        if self.mode == "MIN_N" and self.min_approvals < 1:
            raise ApprovalError("APPROVAL_MIN_APPROVALS_INVALID")
        if self.mode == "ROLE_BASED_SEQUENCE" and not self.sequence_roles:
            raise ApprovalError("APPROVAL_SEQUENCE_ROLES_REQUIRED")


@dataclass(frozen=True, slots=True)
class ApprovalFeedback:
    comment: str
    node_refs: tuple[str, ...] = ()
    region_refs: tuple[str, ...] = ()
    requested_changes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        normalized = self.comment.strip()
        if not normalized and not self.requested_changes:
            raise ApprovalError("APPROVAL_CHANGES_FEEDBACK_REQUIRED")
        if len(normalized) > 4000:
            raise ApprovalError("APPROVAL_FEEDBACK_TOO_LONG")
        if len(self.node_refs) > 100 or len(self.region_refs) > 100:
            raise ApprovalError("APPROVAL_FEEDBACK_REFS_TOO_MANY")


@dataclass(frozen=True, slots=True)
class ApprovalDecisionRecord:
    decision_id: str
    approval_id: str
    actor_id: str
    actor_roles: tuple[str, ...]
    decision: ApprovalDecision
    reason: str | None
    decided_subject_version: str
    idempotency_key: str
    created_at: str


@dataclass(frozen=True, slots=True)
class ApprovalRecord:
    approval_id: str
    organization_id: str
    project_id: str
    approval_type: ApprovalType
    subject: ApprovalSubject
    status: ApprovalStatus
    requested_by: str
    policy: ApprovalPolicy
    payload_summary: str
    agent_run_id: str | None
    task_id: str | None
    expires_at: str | None
    created_at: str
    resolved_at: str | None = None
    resolved_by: str | None = None
    decisions: tuple[ApprovalDecisionRecord, ...] = ()
    feedback: ApprovalFeedback | None = None
    superseded_by: str | None = None


@dataclass(frozen=True, slots=True)
class ApprovalAuditEvent:
    event_id: str
    organization_id: str
    project_id: str
    approval_id: str
    event_type: str
    actor_id: str
    subject_type: str
    subject_id: str
    subject_version: str
    safe_metadata: dict[str, str | int | bool | None]
    created_at: str


@dataclass(frozen=True, slots=True)
class ApprovalNotification:
    notification_id: str
    organization_id: str
    project_id: str
    recipient_scope: str
    approval_id: str
    safe_summary: str
    created_at: str


@dataclass(frozen=True, slots=True)
class ApprovalResumeEnvelope:
    approval_id: str
    decision: ApprovalDecision
    status: ApprovalStatus
    subject_type: str
    subject_id: str
    subject_version: str
    feedback: ApprovalFeedback | None


class ApprovalRepository(Protocol):
    def get(self, organization_id: str, project_id: str, approval_id: str) -> ApprovalRecord | None: ...

    def list_project(self, organization_id: str, project_id: str) -> tuple[ApprovalRecord, ...]: ...

    def save(self, approval: ApprovalRecord) -> None: ...

    def approval_for_idempotency_key(
        self, organization_id: str, idempotency_key: str
    ) -> str | None: ...

    def record_idempotency_key(
        self, organization_id: str, idempotency_key: str, approval_id: str
    ) -> None: ...


class ApprovalSubjectPort(Protocol):
    def exists(self, organization_id: str, project_id: str, subject: ApprovalSubject) -> bool: ...


class ApprovalRunPort(Protocol):
    def can_resume(self, organization_id: str, project_id: str, agent_run_id: str) -> bool: ...


class ApprovalResumePort(Protocol):
    def resume(self, agent_run_id: str, envelope: ApprovalResumeEnvelope) -> None: ...


class ApprovalAuditPort(Protocol):
    def record(self, event: ApprovalAuditEvent) -> None: ...


class ApprovalNotificationPort(Protocol):
    def send(self, notification: ApprovalNotification) -> None: ...


class ApprovalChangesPort(Protocol):
    def create_change_tasks(
        self,
        organization_id: str,
        project_id: str,
        approval_id: str,
        subject: ApprovalSubject,
        feedback: ApprovalFeedback,
    ) -> tuple[str, ...]: ...


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _require_exact_version(value: str) -> None:
    normalized = value.strip()
    if not normalized or normalized.lower() in FLOATING_VERSIONS:
        raise ApprovalError("APPROVAL_SUBJECT_VERSION_MUST_BE_EXACT")


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class ApprovalEngine:
    def __init__(
        self,
        *,
        repository: ApprovalRepository,
        subjects: ApprovalSubjectPort,
        runs: ApprovalRunPort,
        resume: ApprovalResumePort,
        audit: ApprovalAuditPort,
        notifications: ApprovalNotificationPort,
        changes: ApprovalChangesPort,
    ) -> None:
        self._repository = repository
        self._subjects = subjects
        self._runs = runs
        self._resume = resume
        self._audit = audit
        self._notifications = notifications
        self._changes = changes

    def request(
        self,
        actor: ApprovalActor,
        *,
        project_id: str,
        approval_type: ApprovalType,
        subject: ApprovalSubject,
        policy: ApprovalPolicy,
        payload_summary: str,
        agent_run_id: str | None = None,
        task_id: str | None = None,
        expires_at: str | None = None,
    ) -> ApprovalRecord:
        if not payload_summary.strip():
            raise ApprovalError("APPROVAL_SUMMARY_REQUIRED")
        if expires_at is not None and _parse_time(expires_at) <= datetime.now(UTC):
            raise ApprovalError("APPROVAL_EXPIRY_MUST_BE_FUTURE")
        if not self._subjects.exists(actor.organization_id, project_id, subject):
            raise ApprovalError("APPROVAL_STALE", 409)
        if agent_run_id is not None and not self._runs.can_resume(
            actor.organization_id, project_id, agent_run_id
        ):
            raise ApprovalError("APPROVAL_RUN_NOT_RESUMABLE", 409)

        approval_id = str(uuid4())
        approval = ApprovalRecord(
            approval_id=approval_id,
            organization_id=actor.organization_id,
            project_id=project_id,
            approval_type=approval_type,
            subject=subject,
            status="PENDING",
            requested_by=actor.actor_id,
            policy=policy,
            payload_summary=payload_summary.strip(),
            agent_run_id=agent_run_id,
            task_id=task_id,
            expires_at=expires_at,
            created_at=_now(),
        )
        self._supersede_prior_pending(actor, approval)
        self._repository.save(approval)
        self._record(actor, approval, "APPROVAL_REQUESTED", {"policy_mode": policy.mode})
        self._notifications.send(
            ApprovalNotification(
                notification_id=str(uuid4()),
                organization_id=actor.organization_id,
                project_id=project_id,
                recipient_scope=policy.required_permission,
                approval_id=approval_id,
                safe_summary=f"Approval required: {approval_type} · {subject.subject_version}",
                created_at=_now(),
            )
        )
        return approval

    def get(self, actor: ApprovalActor, project_id: str, approval_id: str) -> ApprovalRecord:
        approval = self._require_approval(actor.organization_id, project_id, approval_id)
        return self._expire_if_due(actor, approval)

    def list_project(self, actor: ApprovalActor, project_id: str) -> tuple[ApprovalRecord, ...]:
        return tuple(
            self._expire_if_due(actor, item)
            for item in self._repository.list_project(actor.organization_id, project_id)
        )

    def decide(
        self,
        actor: ApprovalActor,
        *,
        project_id: str,
        approval_id: str,
        decision: ApprovalDecision,
        idempotency_key: str,
        reason: str | None = None,
        feedback: ApprovalFeedback | None = None,
    ) -> ApprovalRecord:
        if not idempotency_key.strip():
            raise ApprovalError("APPROVAL_IDEMPOTENCY_KEY_REQUIRED")
        prior_id = self._repository.approval_for_idempotency_key(
            actor.organization_id, idempotency_key
        )
        if prior_id is not None:
            if prior_id != approval_id:
                raise ApprovalError("APPROVAL_IDEMPOTENCY_KEY_REUSED", 409)
            return self._require_approval(actor.organization_id, project_id, approval_id)

        approval = self._expire_if_due(
            actor, self._require_approval(actor.organization_id, project_id, approval_id)
        )
        if approval.status != "PENDING":
            raise ApprovalError("APPROVAL_STALE", 409)
        self._authorize(actor, approval)
        if not self._subjects.exists(actor.organization_id, project_id, approval.subject):
            raise ApprovalError("APPROVAL_STALE", 409)
        if approval.agent_run_id is not None and not self._runs.can_resume(
            actor.organization_id, project_id, approval.agent_run_id
        ):
            raise ApprovalError("APPROVAL_STALE", 409)
        if decision == "REQUEST_CHANGES" and feedback is None:
            raise ApprovalError("APPROVAL_CHANGES_FEEDBACK_REQUIRED")
        if decision != "REQUEST_CHANGES" and feedback is not None:
            raise ApprovalError("APPROVAL_FEEDBACK_ONLY_FOR_CHANGES")

        self._validate_sequence(actor, approval, decision)
        record = ApprovalDecisionRecord(
            decision_id=str(uuid4()),
            approval_id=approval.approval_id,
            actor_id=actor.actor_id,
            actor_roles=actor.roles,
            decision=decision,
            reason=reason.strip()[:1000] if reason and reason.strip() else None,
            decided_subject_version=approval.subject.subject_version,
            idempotency_key=idempotency_key,
            created_at=_now(),
        )
        with_decision = replace(approval, decisions=(*approval.decisions, record))
        final_status = self._aggregate(with_decision, decision)
        updated = replace(
            with_decision,
            status=final_status,
            resolved_at=_now() if final_status != "PENDING" else None,
            resolved_by=actor.actor_id if final_status != "PENDING" else None,
            feedback=feedback if final_status == "CHANGES_REQUESTED" else None,
        )
        self._repository.save(updated)
        self._repository.record_idempotency_key(
            actor.organization_id, idempotency_key, approval_id
        )
        self._record(
            actor,
            updated,
            "APPROVAL_DECISION_RECORDED" if final_status == "PENDING" else f"APPROVAL_{final_status}",
            {"decision": decision, "policy_mode": approval.policy.mode},
        )

        if final_status == "CHANGES_REQUESTED" and feedback is not None:
            task_ids = self._changes.create_change_tasks(
                actor.organization_id, project_id, approval_id, approval.subject, feedback
            )
            self._record(actor, updated, "APPROVAL_CHANGE_TASKS_CREATED", {"task_count": len(task_ids)})
        if final_status in {"APPROVED", "REJECTED", "CHANGES_REQUESTED"}:
            self._resume_graph(updated, decision, feedback)
        return updated

    def cancel(
        self, actor: ApprovalActor, *, project_id: str, approval_id: str, reason: str | None = None
    ) -> ApprovalRecord:
        approval = self._require_approval(actor.organization_id, project_id, approval_id)
        if approval.status != "PENDING":
            raise ApprovalError("APPROVAL_STALE", 409)
        if actor.actor_id != approval.requested_by and "project.write" not in actor.permissions:
            raise ApprovalError("APPROVAL_FORBIDDEN", 403)
        updated = replace(
            approval, status="CANCELLED", resolved_at=_now(), resolved_by=actor.actor_id
        )
        self._repository.save(updated)
        self._record(actor, updated, "APPROVAL_CANCELLED", {"has_reason": bool(reason and reason.strip())})
        return updated

    def expire_due(self, actor: ApprovalActor, project_id: str) -> tuple[ApprovalRecord, ...]:
        return self.list_project(actor, project_id)

    def _expire_if_due(self, actor: ApprovalActor, approval: ApprovalRecord) -> ApprovalRecord:
        if approval.status != "PENDING" or approval.expires_at is None:
            return approval
        if _parse_time(approval.expires_at) > datetime.now(UTC):
            return approval
        updated = replace(approval, status="EXPIRED", resolved_at=_now())
        self._repository.save(updated)
        self._record(actor, updated, "APPROVAL_EXPIRED", {})
        return updated

    def _supersede_prior_pending(self, actor: ApprovalActor, incoming: ApprovalRecord) -> None:
        for item in self._repository.list_project(actor.organization_id, incoming.project_id):
            if (
                item.status == "PENDING"
                and item.subject.subject_type == incoming.subject.subject_type
                and item.subject.subject_id == incoming.subject.subject_id
                and item.subject.subject_version != incoming.subject.subject_version
            ):
                updated = replace(
                    item,
                    status="SUPERSEDED",
                    resolved_at=_now(),
                    superseded_by=incoming.approval_id,
                )
                self._repository.save(updated)
                self._record(actor, updated, "APPROVAL_SUPERSEDED", {"new_approval_id": incoming.approval_id})

    @staticmethod
    def _authorize(actor: ApprovalActor, approval: ApprovalRecord) -> None:
        if approval.policy.required_permission not in actor.permissions:
            raise ApprovalError("APPROVAL_FORBIDDEN", 403)
        if approval.policy.required_roles and not set(actor.roles).intersection(approval.policy.required_roles):
            raise ApprovalError("APPROVAL_FORBIDDEN", 403)

    @staticmethod
    def _validate_sequence(
        actor: ApprovalActor, approval: ApprovalRecord, decision: ApprovalDecision
    ) -> None:
        if decision != "APPROVE" or approval.policy.mode != "ROLE_BASED_SEQUENCE":
            return
        approved_roles = {
            role
            for item in approval.decisions
            if item.decision == "APPROVE"
            for role in item.actor_roles
        }
        next_role = next(
            (role for role in approval.policy.sequence_roles if role not in approved_roles), None
        )
        if next_role is not None and next_role not in actor.roles:
            raise ApprovalError("APPROVAL_SEQUENCE_ROLE_REQUIRED", 403)

    @staticmethod
    def _aggregate(approval: ApprovalRecord, latest: ApprovalDecision) -> ApprovalStatus:
        if latest == "REJECT":
            return "REJECTED"
        if latest == "REQUEST_CHANGES":
            return "CHANGES_REQUESTED"
        approvals = [item for item in approval.decisions if item.decision == "APPROVE"]
        unique_actors = {item.actor_id for item in approvals}
        policy = approval.policy
        if policy.mode == "ANY_ONE":
            return "APPROVED"
        if policy.mode == "MIN_N":
            return "APPROVED" if len(unique_actors) >= policy.min_approvals else "PENDING"
        approved_roles = {role for item in approvals for role in item.actor_roles}
        if policy.mode == "ALL":
            required = set(policy.required_roles)
            return "APPROVED" if required and required.issubset(approved_roles) else "PENDING"
        if policy.mode == "ROLE_BASED_SEQUENCE":
            required = set(policy.sequence_roles)
            return "APPROVED" if required.issubset(approved_roles) else "PENDING"
        return "PENDING"

    def _resume_graph(
        self,
        approval: ApprovalRecord,
        decision: ApprovalDecision,
        feedback: ApprovalFeedback | None,
    ) -> None:
        if approval.agent_run_id is None:
            return
        self._resume.resume(
            approval.agent_run_id,
            ApprovalResumeEnvelope(
                approval_id=approval.approval_id,
                decision=decision,
                status=approval.status,
                subject_type=approval.subject.subject_type,
                subject_id=approval.subject.subject_id,
                subject_version=approval.subject.subject_version,
                feedback=feedback,
            ),
        )

    def _require_approval(
        self, organization_id: str, project_id: str, approval_id: str
    ) -> ApprovalRecord:
        approval = self._repository.get(organization_id, project_id, approval_id)
        if approval is None:
            raise ApprovalError("APPROVAL_NOT_FOUND", 404)
        return approval

    def _record(
        self,
        actor: ApprovalActor,
        approval: ApprovalRecord,
        event_type: str,
        metadata: dict[str, str | int | bool | None],
    ) -> None:
        self._audit.record(
            ApprovalAuditEvent(
                event_id=str(uuid4()),
                organization_id=approval.organization_id,
                project_id=approval.project_id,
                approval_id=approval.approval_id,
                event_type=event_type,
                actor_id=actor.actor_id,
                subject_type=approval.subject.subject_type,
                subject_id=approval.subject.subject_id,
                subject_version=approval.subject.subject_version,
                safe_metadata=metadata,
                created_at=_now(),
            )
        )


class InMemoryApprovalRepository:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str, str], ApprovalRecord] = {}
        self.idempotency: dict[tuple[str, str], str] = {}

    def get(self, organization_id: str, project_id: str, approval_id: str) -> ApprovalRecord | None:
        return self.records.get((organization_id, project_id, approval_id))

    def list_project(self, organization_id: str, project_id: str) -> tuple[ApprovalRecord, ...]:
        records = [
            item
            for (org, project, _), item in self.records.items()
            if org == organization_id and project == project_id
        ]
        return tuple(sorted(records, key=lambda item: item.created_at, reverse=True))

    def save(self, approval: ApprovalRecord) -> None:
        self.records[(approval.organization_id, approval.project_id, approval.approval_id)] = approval

    def approval_for_idempotency_key(self, organization_id: str, idempotency_key: str) -> str | None:
        return self.idempotency.get((organization_id, idempotency_key))

    def record_idempotency_key(self, organization_id: str, idempotency_key: str, approval_id: str) -> None:
        self.idempotency[(organization_id, idempotency_key)] = approval_id


class InMemoryApprovalSubjects:
    def __init__(self, subjects: tuple[tuple[str, str, str, str, str], ...] = ()) -> None:
        self.subjects = set(subjects)

    def add(self, organization_id: str, project_id: str, subject: ApprovalSubject) -> None:
        self.subjects.add(
            (organization_id, project_id, subject.subject_type, subject.subject_id, subject.subject_version)
        )

    def exists(self, organization_id: str, project_id: str, subject: ApprovalSubject) -> bool:
        return (
            organization_id,
            project_id,
            subject.subject_type,
            subject.subject_id,
            subject.subject_version,
        ) in self.subjects


class InMemoryApprovalRuns:
    def __init__(self, resumable: frozenset[tuple[str, str, str]] = frozenset()) -> None:
        self.resumable = set(resumable)

    def can_resume(self, organization_id: str, project_id: str, agent_run_id: str) -> bool:
        return (organization_id, project_id, agent_run_id) in self.resumable


class RecordingApprovalResume:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ApprovalResumeEnvelope]] = []

    def resume(self, agent_run_id: str, envelope: ApprovalResumeEnvelope) -> None:
        self.calls.append((agent_run_id, envelope))


class RecordingApprovalAudit:
    def __init__(self) -> None:
        self.events: list[ApprovalAuditEvent] = []

    def record(self, event: ApprovalAuditEvent) -> None:
        self.events.append(event)


class RecordingApprovalNotifications:
    def __init__(self) -> None:
        self.notifications: list[ApprovalNotification] = []

    def send(self, notification: ApprovalNotification) -> None:
        self.notifications.append(notification)


class RecordingApprovalChanges:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, ApprovalSubject, ApprovalFeedback]] = []

    def create_change_tasks(
        self,
        organization_id: str,
        project_id: str,
        approval_id: str,
        subject: ApprovalSubject,
        feedback: ApprovalFeedback,
    ) -> tuple[str, ...]:
        self.calls.append((organization_id, project_id, approval_id, subject, feedback))
        return (f"approval-change-{approval_id}",)
