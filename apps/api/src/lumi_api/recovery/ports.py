from __future__ import annotations

from typing import Protocol
from uuid import UUID

from .model import (
    AgentControlEvidence,
    ArtifactObjectEvidence,
    IdempotencyEvidence,
    ObjectVerification,
    RuntimeJobEvidence,
)


class RecoveryScannerPort(Protocol):
    def scan_runtime_jobs(
        self,
        *,
        organization_id: UUID,
    ) -> tuple[RuntimeJobEvidence, ...]: ...

    def resolve_operation(
        self,
        *,
        organization_id: UUID,
        operation_id: UUID | None,
    ) -> IdempotencyEvidence | None: ...

    def scan_idempotency_operations(
        self,
        *,
        organization_id: UUID,
    ) -> tuple[IdempotencyEvidence, ...]: ...

    def scan_agent_controls(
        self,
        *,
        organization_id: UUID,
    ) -> tuple[AgentControlEvidence, ...]: ...


class ObjectVerificationPort(Protocol):
    async def verify(self, evidence: ArtifactObjectEvidence) -> ObjectVerification: ...


class RuntimeRedispatchPort(Protocol):
    async def redispatch(
        self,
        *,
        job_id: UUID,
        operation_id: UUID | None,
    ) -> None:
        """Redispatch the same durable runtime job; never mint a replacement identity."""
        ...


class AgentRecoveryPort(Protocol):
    async def resume_existing(
        self,
        *,
        agent_run_id: UUID,
        checkpoint_id: str | None,
        checkpoint_namespace: str,
        resume_version: int,
    ) -> None:
        """Resume an existing durable run/checkpoint, never create a new AgentRun."""
        ...


class ExternalReconcilePort(Protocol):
    async def reconcile_existing(
        self,
        *,
        operation_id: UUID,
        provider_request_id: str,
    ) -> None:
        """Poll/reconcile an existing provider request; submitting a new request is forbidden."""
        ...
