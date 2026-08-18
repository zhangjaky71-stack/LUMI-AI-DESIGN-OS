from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from .model import (
    ArtifactObjectEvidence,
    RecoveryDecision,
    RecoveryDisposition,
    RecoveryPlan,
    RecoverySubjectType,
)
from .policy import (
    classify_agent_control,
    classify_idempotency_operation,
    classify_object_verification,
    classify_runtime_job,
)
from .ports import (
    AgentRecoveryPort,
    ExternalReconcilePort,
    ObjectVerificationPort,
    RecoveryScannerPort,
    RuntimeRedispatchPort,
)


class RecoveryActionDenied(RuntimeError):
    pass


class RecoveryService:
    def __init__(
        self,
        *,
        scanner: RecoveryScannerPort,
        object_verifier: ObjectVerificationPort | None = None,
        runtime_redispatch: RuntimeRedispatchPort | None = None,
        agent_recovery: AgentRecoveryPort | None = None,
        external_reconcile: ExternalReconcilePort | None = None,
    ) -> None:
        self.scanner = scanner
        self.object_verifier = object_verifier
        self.runtime_redispatch = runtime_redispatch
        self.agent_recovery = agent_recovery
        self.external_reconcile = external_reconcile

    async def build_plan(
        self,
        *,
        organization_id: UUID,
        artifact_objects: tuple[ArtifactObjectEvidence, ...] = (),
        now: datetime | None = None,
    ) -> RecoveryPlan:
        current = now or datetime.now(UTC)
        decisions: list[RecoveryDecision] = []
        referenced_operations: set[UUID] = set()

        for runtime in self.scanner.scan_runtime_jobs(
            organization_id=organization_id
        ):
            operation = self.scanner.resolve_operation(
                organization_id=organization_id,
                operation_id=runtime.operation_id,
            )
            if operation is not None:
                referenced_operations.add(operation.operation_id)
            decisions.append(
                classify_runtime_job(runtime, operation, now=current)
            )

        for operation in self.scanner.scan_idempotency_operations(
            organization_id=organization_id
        ):
            if operation.operation_id in referenced_operations:
                continue
            decisions.append(
                classify_idempotency_operation(operation, now=current)
            )

        for agent in self.scanner.scan_agent_controls(
            organization_id=organization_id
        ):
            decisions.append(classify_agent_control(agent))

        if artifact_objects:
            if self.object_verifier is None:
                for item in artifact_objects:
                    decisions.append(
                        RecoveryDecision(
                            subject_type=RecoverySubjectType.ARTIFACT_FILE,
                            subject_id=f"{item.artifact_version_id}:{item.file_id}",
                            disposition=RecoveryDisposition.VERIFY_OBJECT,
                            reason_code="OBJECT_VERIFIER_NOT_COMPOSED",
                        )
                    )
            else:
                for item in artifact_objects:
                    measured = await self.object_verifier.verify(item)
                    decisions.append(classify_object_verification(item, measured))

        return RecoveryPlan(
            organization_id=organization_id,
            generated_at=current,
            decisions=tuple(
                sorted(
                    decisions,
                    key=lambda item: (item.subject_type.value, item.subject_id),
                )
            ),
        )

    async def execute_decision(
        self,
        decision: RecoveryDecision,
        *,
        runtime_job_id: UUID | None = None,
        agent_run_id: UUID | None = None,
        checkpoint_id: str | None = None,
        checkpoint_namespace: str = "",
        resume_version: int = 1,
    ) -> None:
        """Execute only dispositions that preserve durable identities.

        REVIEW_REQUIRED/VERIFY_OBJECT/TERMINAL/SKIP never cause side effects here.
        The method intentionally requires exact durable identifiers rather than
        reconstructing them from labels or queue payloads.
        """
        if decision.disposition is RecoveryDisposition.REQUEUE_SAFE:
            if self.runtime_redispatch is None or runtime_job_id is None:
                raise RecoveryActionDenied("RECOVERY_RUNTIME_REDISPATCH_NOT_COMPOSED")
            await self.runtime_redispatch.redispatch(
                job_id=runtime_job_id,
                operation_id=decision.preserve_operation_id,
            )
            return
        if decision.disposition is RecoveryDisposition.RESUME_SAFE:
            if self.agent_recovery is None or agent_run_id is None:
                raise RecoveryActionDenied("RECOVERY_AGENT_RESUME_NOT_COMPOSED")
            await self.agent_recovery.resume_existing(
                agent_run_id=agent_run_id,
                checkpoint_id=checkpoint_id,
                checkpoint_namespace=checkpoint_namespace,
                resume_version=resume_version,
            )
            return
        if decision.disposition is RecoveryDisposition.RECONCILE_EXTERNAL:
            if (
                self.external_reconcile is None
                or decision.preserve_operation_id is None
                or decision.preserve_provider_request_id is None
            ):
                raise RecoveryActionDenied("RECOVERY_EXTERNAL_RECONCILE_NOT_COMPOSED")
            await self.external_reconcile.reconcile_existing(
                operation_id=decision.preserve_operation_id,
                provider_request_id=decision.preserve_provider_request_id,
            )
            return
        raise RecoveryActionDenied(
            f"RECOVERY_DISPOSITION_NOT_EXECUTABLE:{decision.disposition.value}"
        )
