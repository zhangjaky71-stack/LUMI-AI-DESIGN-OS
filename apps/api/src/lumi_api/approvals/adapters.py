from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable, Protocol
from uuid import UUID

from lumi_api.artifact_engine import ArtifactEngineService
from lumi_api.artifacts.models import ArtifactVersionStatus

from .contracts import ApprovalDecisionKind


class AgentRunControlRuntime(Protocol):
    async def resume(
        self,
        *,
        organization_id: UUID,
        agent_run_id: UUID,
        operation_id: UUID,
        resume_version: int,
        interrupt_id: str,
        kind: str,
        value: Any,
        request_context: Any,
    ) -> dict[str, Any]: ...


class ArtifactEngineApprovalAdapter:
    """Idempotent adapter from formal Approval effects to ArtifactEngine status."""

    def __init__(self, service: ArtifactEngineService) -> None:
        self.service = service

    async def approve_exact_artifact_version(
        self,
        *,
        organization_id: UUID,
        approval_id: UUID,
        artifact_version_id: UUID,
        approved_by_id: str,
    ) -> None:
        current = self.service.repository.get_version(artifact_version_id)
        if current.organization_id != organization_id:
            raise RuntimeError("APPROVAL_ARTIFACT_TENANT_MISMATCH")
        if current.status == ArtifactVersionStatus.APPROVED:
            return
        if current.status != ArtifactVersionStatus.READY:
            raise RuntimeError("APPROVAL_ARTIFACT_NOT_READY")
        self.service.approve_version(
            artifact_version_id,
            approved_by_id=approved_by_id,
            approved_at=datetime.now(UTC),
            validation_ref=f"approval:{approval_id}",
        )


class AgentRunApprovalResumeAdapter:
    """Bridge formal approval decisions back into the existing LangGraph control plane."""

    def __init__(
        self,
        runtime: AgentRunControlRuntime,
        request_context_factory: Callable[[UUID, UUID], Any],
    ) -> None:
        self.runtime = runtime
        self.request_context_factory = request_context_factory

    async def resume_from_approval(
        self,
        *,
        organization_id: UUID,
        approval_id: UUID,
        agent_run_id: UUID,
        operation_id: UUID,
        resume_version: int,
        interrupt_id: str,
        decision: ApprovalDecisionKind,
        reason: str | None,
        feedback: dict[str, Any],
    ) -> None:
        await self.runtime.resume(
            organization_id=organization_id,
            agent_run_id=agent_run_id,
            operation_id=operation_id,
            resume_version=resume_version,
            interrupt_id=interrupt_id,
            kind="approval",
            value={
                "approval_id": str(approval_id),
                "decision": decision.value,
                "reason": reason,
                "feedback": feedback,
            },
            request_context=self.request_context_factory(organization_id, approval_id),
        )
