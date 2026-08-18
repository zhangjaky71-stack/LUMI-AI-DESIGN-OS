from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from .contracts import ApprovalDecisionKind, ApprovalEffect, ApprovalEffectStatus, ApprovalEffectType
from .repository import ApprovalConflict, ApprovalNotFound, PostgresApprovalRepository


class ArtifactApprovalEffectPort(Protocol):
    async def approve_exact_artifact_version(
        self,
        *,
        organization_id: UUID,
        approval_id: UUID,
        artifact_version_id: UUID,
        approved_by_id: str,
    ) -> None: ...


class AgentApprovalResumePort(Protocol):
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
    ) -> None: ...


class ApprovalEffectProcessor:
    """Process durable approval effects idempotently across runtime restarts.

    The approval decision is already canonical before this processor runs. A crash
    therefore leaves an effect in PENDING/RUNNING/FAILED state rather than losing
    the human decision. Production composition can retry these rows safely.
    """

    def __init__(
        self,
        session: Session,
        organization_id: UUID,
        *,
        artifact_port: ArtifactApprovalEffectPort | None = None,
        agent_port: AgentApprovalResumePort | None = None,
    ) -> None:
        self.session = session
        self.organization_id = organization_id
        self.artifact_port = artifact_port
        self.agent_port = agent_port

    async def process(self, effect_id: UUID) -> ApprovalEffect:
        effect = self._claim(effect_id)
        if effect.status == ApprovalEffectStatus.COMPLETED:
            return effect
        try:
            if effect.effect_type == ApprovalEffectType.ARTIFACT_VERSION_APPROVE:
                if self.artifact_port is None:
                    raise RuntimeError("ARTIFACT_APPROVAL_EFFECT_PORT_NOT_COMPOSED")
                await self.artifact_port.approve_exact_artifact_version(
                    organization_id=effect.organization_id,
                    approval_id=effect.approval_id,
                    artifact_version_id=UUID(str(effect.payload["artifact_version_id"])),
                    approved_by_id=str(effect.payload["approved_by_id"]),
                )
            elif effect.effect_type == ApprovalEffectType.AGENT_RUN_RESUME:
                if self.agent_port is None:
                    raise RuntimeError("AGENT_APPROVAL_RESUME_PORT_NOT_COMPOSED")
                await self.agent_port.resume_from_approval(
                    organization_id=effect.organization_id,
                    approval_id=effect.approval_id,
                    agent_run_id=UUID(str(effect.payload["agent_run_id"])),
                    operation_id=effect.operation_id,
                    resume_version=int(effect.payload["resume_version"]),
                    interrupt_id=str(effect.payload["interrupt_id"]),
                    decision=ApprovalDecisionKind(str(effect.payload["decision"])),
                    reason=(str(effect.payload["reason"]) if effect.payload.get("reason") else None),
                    feedback=dict(effect.payload.get("feedback") or {}),
                )
            else:
                raise RuntimeError("UNSUPPORTED_APPROVAL_EFFECT_TYPE")
        except Exception as exc:
            self._mark_failed(effect.id, str(exc))
            raise
        self._mark_completed(effect.id)
        return self._get(effect.id)

    def _claim(self, effect_id: UUID) -> ApprovalEffect:
        now = datetime.now(UTC)
        with self.session.begin():
            row = self.session.execute(
                text(
                    """
                    SELECT * FROM approval_effects
                    WHERE id=:id AND organization_id=:organization_id
                    FOR UPDATE
                    """
                ),
                {"id": effect_id, "organization_id": self.organization_id},
            ).mappings().one_or_none()
            if row is None:
                raise ApprovalNotFound("APPROVAL_EFFECT_NOT_FOUND")
            current = ApprovalEffectStatus(str(row["status"]))
            if current == ApprovalEffectStatus.COMPLETED:
                return PostgresApprovalRepository._effect(row)
            if current == ApprovalEffectStatus.RUNNING:
                raise ApprovalConflict("APPROVAL_EFFECT_ALREADY_RUNNING")
            if current == ApprovalEffectStatus.CANCELLED:
                raise ApprovalConflict("APPROVAL_EFFECT_CANCELLED")
            self.session.execute(
                text(
                    """
                    UPDATE approval_effects
                    SET status='RUNNING', attempt_count=attempt_count+1,
                        last_error=NULL, updated_at=:updated_at
                    WHERE id=:id AND organization_id=:organization_id
                    """
                ),
                {
                    "updated_at": now,
                    "id": effect_id,
                    "organization_id": self.organization_id,
                },
            )
        return self._get(effect_id)

    def _mark_completed(self, effect_id: UUID) -> None:
        now = datetime.now(UTC)
        with self.session.begin():
            self.session.execute(
                text(
                    """
                    UPDATE approval_effects
                    SET status='COMPLETED', completed_at=:now,
                        updated_at=:now, last_error=NULL
                    WHERE id=:id AND organization_id=:organization_id
                    """
                ),
                {"now": now, "id": effect_id, "organization_id": self.organization_id},
            )

    def _mark_failed(self, effect_id: UUID, error: str) -> None:
        now = datetime.now(UTC)
        with self.session.begin():
            self.session.execute(
                text(
                    """
                    UPDATE approval_effects
                    SET status='FAILED', last_error=:error, updated_at=:now
                    WHERE id=:id AND organization_id=:organization_id
                    """
                ),
                {
                    "error": error[:2000],
                    "now": now,
                    "id": effect_id,
                    "organization_id": self.organization_id,
                },
            )

    def _get(self, effect_id: UUID) -> ApprovalEffect:
        row = self.session.execute(
            text(
                "SELECT * FROM approval_effects WHERE id=:id AND organization_id=:organization_id"
            ),
            {"id": effect_id, "organization_id": self.organization_id},
        ).mappings().one_or_none()
        if row is None:
            raise ApprovalNotFound("APPROVAL_EFFECT_NOT_FOUND")
        return PostgresApprovalRepository._effect(row)
