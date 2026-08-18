from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from lumi_api.persistence.models_control_plane import (
    AgentGraphDefinitionModel,
    AgentRunControlModel,
)
from lumi_api.persistence.models_execution import IdempotencyOperationModel
from lumi_api.persistence.models_queue_runtime import RuntimeJobModel

from .model import AgentControlEvidence, IdempotencyEvidence, RuntimeJobEvidence


class PostgresRecoveryScanner:
    """Reads existing durable truth; it does not create a second recovery state machine."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def scan_runtime_jobs(self, *, organization_id: UUID) -> tuple[RuntimeJobEvidence, ...]:
        rows = self.session.scalars(
            select(RuntimeJobModel)
            .where(
                RuntimeJobModel.organization_id == organization_id,
                RuntimeJobModel.status.in_(("pending", "running", "retrying")),
            )
            .order_by(RuntimeJobModel.created_at, RuntimeJobModel.id)
        ).all()
        return tuple(self._runtime(row) for row in rows)

    def resolve_operation(
        self,
        *,
        organization_id: UUID,
        operation_id: UUID | None,
    ) -> IdempotencyEvidence | None:
        if operation_id is None:
            return None
        row = self.session.get(IdempotencyOperationModel, operation_id)
        if row is None or row.organization_id != organization_id:
            return None
        return self._operation(row)

    def scan_idempotency_operations(
        self,
        *,
        organization_id: UUID,
    ) -> tuple[IdempotencyEvidence, ...]:
        rows = self.session.scalars(
            select(IdempotencyOperationModel)
            .where(
                IdempotencyOperationModel.organization_id == organization_id,
                IdempotencyOperationModel.status.in_(
                    ("new", "in_progress", "failed_retryable")
                ),
            )
            .order_by(IdempotencyOperationModel.created_at, IdempotencyOperationModel.id)
        ).all()
        return tuple(self._operation(row) for row in rows)

    def scan_agent_controls(
        self,
        *,
        organization_id: UUID,
    ) -> tuple[AgentControlEvidence, ...]:
        controls = self.session.scalars(
            select(AgentRunControlModel)
            .where(
                AgentRunControlModel.organization_id == organization_id,
                AgentRunControlModel.control_status.in_(
                    (
                        "pending",
                        "running",
                        "waiting_user",
                        "waiting_external",
                        "cancel_requested",
                    )
                ),
            )
            .order_by(AgentRunControlModel.updated_at, AgentRunControlModel.agent_run_id)
        ).all()
        return tuple(self._agent(row) for row in controls)

    def _agent(self, row: AgentRunControlModel) -> AgentControlEvidence:
        definition = self.session.scalar(
            select(AgentGraphDefinitionModel).where(
                AgentGraphDefinitionModel.graph_key == row.graph_key,
                AgentGraphDefinitionModel.graph_version == row.graph_version,
            )
        )
        return AgentControlEvidence(
            agent_run_id=row.agent_run_id,
            organization_id=row.organization_id,
            project_id=row.project_id,
            graph_key=row.graph_key,
            graph_version=row.graph_version,
            graph_definition_hash=row.graph_definition_hash,
            control_status=row.control_status,
            checkpoint_id=row.checkpoint_id,
            checkpoint_namespace=row.checkpoint_namespace,
            resume_version=row.resume_version,
            current_graph_definition_hash=(
                definition.content_hash if definition is not None else None
            ),
            current_graph_enabled=bool(definition is not None and definition.enabled),
        )

    @staticmethod
    def _runtime(row: RuntimeJobModel) -> RuntimeJobEvidence:
        if row.operation_id is None:
            # RuntimeJobEvidence keeps a UUID field so recovery decisions can state the
            # exact preserved identity. A nil UUID means the legacy job has no durable
            # operation identity and therefore cannot be treated as paid-idempotent.
            operation_id = UUID(int=0)
        else:
            operation_id = row.operation_id
        return RuntimeJobEvidence(
            job_id=row.id,
            organization_id=row.organization_id,
            project_id=row.project_id,
            operation_id=operation_id,
            job_kind=row.job_kind,
            status=row.status,
            attempt_count=row.attempt_count,
            max_attempts=row.max_attempts,
            started_at=row.started_at,
            next_retry_at=row.next_retry_at,
        )

    @staticmethod
    def _operation(row: IdempotencyOperationModel) -> IdempotencyEvidence:
        return IdempotencyEvidence(
            operation_id=row.id,
            organization_id=row.organization_id,
            operation_type=row.operation_type,
            status=row.status,
            paid=row.paid,
            side_effect_kind=row.side_effect_kind,
            compensation_mode=row.compensation_mode,
            lease_owner=row.lease_owner,
            lease_expires_at=row.lease_expires_at,
            provider_request_id=row.provider_request_id,
            result_ref=row.result_ref,
            recovery_state=row.recovery_state,
        )
