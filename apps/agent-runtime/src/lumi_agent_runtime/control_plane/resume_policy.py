from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from .contracts import (
    GraphRunSnapshot,
    InterruptKind,
    ResumeAuthorization,
    ResumeDecision,
    ResumeRequest,
)
from .errors import (
    GraphInterruptNotFoundError,
    GraphResumeDeniedError,
)


@dataclass(frozen=True, slots=True)
class ApprovalDecisionRecord:
    approval_id: UUID
    organization_id: UUID
    project_id: UUID
    agent_run_id: UUID
    status: str
    decision_payload: dict[str, Any]


class ApprovalDecisionReader(Protocol):
    async def get_approval(self, approval_id: UUID) -> ApprovalDecisionRecord: ...


class ResumeInputValidator(Protocol):
    async def validate(
        self,
        *,
        request_key: str,
        schema: dict[str, Any],
        value: Any,
    ) -> Any: ...


class DenyUnknownInputValidator:
    async def validate(
        self,
        *,
        request_key: str,
        schema: dict[str, Any],
        value: Any,
    ) -> Any:
        del request_key, schema, value
        raise GraphResumeDeniedError("input resume validator is not installed")


class PolicyResumeAuthorizer:
    """Maps durable LUMI approvals/input policy to LangGraph resume values."""

    def __init__(
        self,
        *,
        approvals: ApprovalDecisionReader,
        inputs: ResumeInputValidator | None = None,
    ) -> None:
        self.approvals = approvals
        self.inputs = inputs or DenyUnknownInputValidator()

    async def authorize(
        self,
        request: ResumeRequest,
        *,
        current: GraphRunSnapshot,
    ) -> ResumeAuthorization:
        interrupt = next(
            (
                item
                for item in current.interrupts
                if item.interrupt_id == request.interrupt_id
            ),
            None,
        )
        if interrupt is None:
            raise GraphInterruptNotFoundError(request.interrupt_id)
        if not interrupt.resumable:
            return ResumeAuthorization(
                approval_id=None,
                approved=False,
                bound_interrupt_id=interrupt.interrupt_id,
                normalized_value=None,
                reason="interrupt is not resumable",
            )
        if interrupt.kind == InterruptKind.APPROVAL:
            return await self._approval(request, current=current, interrupt=interrupt)
        if interrupt.kind == InterruptKind.INPUT:
            return await self._input(request, interrupt=interrupt)
        return ResumeAuthorization(
            approval_id=None,
            approved=False,
            bound_interrupt_id=interrupt.interrupt_id,
            normalized_value=None,
            reason=f"interrupt kind requires an explicit LUMI policy: {interrupt.kind.value}",
        )

    async def _approval(
        self,
        request: ResumeRequest,
        *,
        current: GraphRunSnapshot,
        interrupt: Any,
    ) -> ResumeAuthorization:
        raw_approval_id = interrupt.payload.get("approval_id")
        try:
            approval_id = UUID(str(raw_approval_id))
        except (ValueError, TypeError) as exc:
            raise GraphResumeDeniedError("approval interrupt has invalid approval_id") from exc
        record = await self.approvals.get_approval(approval_id)
        if (
            record.organization_id != request.organization_id
            or record.project_id != request.project_id
            or record.agent_run_id != request.agent_run_id
            or current.organization_id != request.organization_id
            or current.project_id != request.project_id
        ):
            raise GraphResumeDeniedError("approval does not belong to AgentRun scope")
        normalized_status = record.status.strip().lower()
        if normalized_status not in {"approved", "rejected"}:
            return ResumeAuthorization(
                approval_id=approval_id,
                approved=False,
                bound_interrupt_id=interrupt.interrupt_id,
                normalized_value=None,
                reason="approval is still pending",
            )
        expected_decision = (
            ResumeDecision.APPROVED
            if normalized_status == "approved"
            else ResumeDecision.REJECTED
        )
        if request.decision != expected_decision:
            raise GraphResumeDeniedError(
                "resume decision does not match durable approval decision"
            )
        # `approved=True` means this resume COMMAND is authorized. A durable business
        # decision of REJECTED is encoded in normalized_value and still legitimately
        # resumes the graph down its rejection branch.
        return ResumeAuthorization(
            approval_id=approval_id,
            approved=True,
            bound_interrupt_id=interrupt.interrupt_id,
            normalized_value={
                "decision": normalized_status,
                "approval_id": str(approval_id),
                "payload": dict(record.decision_payload),
            },
        )

    async def _input(
        self,
        request: ResumeRequest,
        *,
        interrupt: Any,
    ) -> ResumeAuthorization:
        if request.decision != ResumeDecision.PROVIDED:
            raise GraphResumeDeniedError("input interrupt requires PROVIDED decision")
        request_key = interrupt.payload.get("request_key")
        schema = interrupt.payload.get("schema", {"type": "string"})
        if not isinstance(request_key, str) or not request_key:
            raise GraphResumeDeniedError("input interrupt has no request_key")
        if not isinstance(schema, dict):
            raise GraphResumeDeniedError("input interrupt schema is invalid")
        normalized = await self.inputs.validate(
            request_key=request_key,
            schema=schema,
            value=request.value,
        )
        return ResumeAuthorization(
            approval_id=None,
            approved=True,
            bound_interrupt_id=interrupt.interrupt_id,
            normalized_value={
                "request_key": request_key,
                "value": normalized,
            },
        )
