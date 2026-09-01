from __future__ import annotations

from typing import Any, Protocol

from langgraph.types import Command, interrupt


class ApprovalSubjectLike(Protocol):
    subject_type: str
    subject_id: str
    subject_version: str


class ApprovalRecordLike(Protocol):
    approval_id: str
    project_id: str
    approval_type: str
    subject: ApprovalSubjectLike
    payload_summary: str
    expires_at: str | None


class ApprovalFeedbackLike(Protocol):
    @property
    def comment(self) -> str: ...

    @property
    def node_refs(self) -> tuple[str, ...]: ...

    @property
    def region_refs(self) -> tuple[str, ...]: ...

    @property
    def requested_changes(self) -> tuple[str, ...]: ...


class ApprovalResumeEnvelopeLike(Protocol):
    @property
    def approval_id(self) -> str: ...

    @property
    def decision(self) -> str: ...

    @property
    def status(self) -> str: ...

    @property
    def subject_type(self) -> str: ...

    @property
    def subject_id(self) -> str: ...

    @property
    def subject_version(self) -> str: ...

    @property
    def feedback(self) -> ApprovalFeedbackLike | None: ...


def interrupt_for_approval(approval: ApprovalRecordLike) -> Any:
    """Create the LangGraph durable interrupt payload after the Approval row exists.

    Only stable identifiers and safe summaries cross the graph boundary. The graph checkpoint stores
    `approval_id`; the Approval database remains the decision source of truth.
    """
    return interrupt(
        {
            "kind": "approval_required",
            "approval_id": approval.approval_id,
            "project_id": approval.project_id,
            "type": approval.approval_type,
            "subject_type": approval.subject.subject_type,
            "subject_id": approval.subject.subject_id,
            "subject_version": approval.subject.subject_version,
            "payload_summary": approval.payload_summary,
            "expires_at": approval.expires_at,
        }
    )


def resume_command(envelope: ApprovalResumeEnvelopeLike) -> Command:
    """Build the exact `Command(resume=...)` payload used after a durable approval decision."""
    return Command(resume=resume_payload(envelope))


def resume_payload(envelope: ApprovalResumeEnvelopeLike) -> dict[str, Any]:
    """Return the serializable resume form for queue/checkpoint adapters."""
    feedback = None
    if envelope.feedback is not None:
        feedback = {
            "comment": envelope.feedback.comment,
            "node_refs": list(envelope.feedback.node_refs),
            "region_refs": list(envelope.feedback.region_refs),
            "requested_changes": list(envelope.feedback.requested_changes),
        }
    return {
        "approval_id": envelope.approval_id,
        "decision": envelope.decision,
        "status": envelope.status,
        "subject_type": envelope.subject_type,
        "subject_id": envelope.subject_id,
        "subject_version": envelope.subject_version,
        "feedback": feedback,
    }
