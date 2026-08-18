from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from lumi_api.governance.redaction import redact_audit_text

from .contracts import (
    AdminDashboard,
    BreakGlassGrant,
    DeadLetterReplayPort,
    FeatureFlag,
    PlatformAdminConflict,
    PlatformAdminForbidden,
    PlatformAdminPrincipal,
    PlatformAdminUnavailable,
    ProviderControlSummary,
    SafeDeadLetter,
    SafeRunSummary,
)
from .repository import PostgresPlatformAdminRepository


class PlatformAdminService:
    def __init__(
        self,
        repository: PostgresPlatformAdminRepository,
        principal: PlatformAdminPrincipal,
        replay_port: DeadLetterReplayPort | None = None,
    ) -> None:
        self.repository = repository
        self.principal = principal
        self.replay_port = replay_port

    def require(self, permission: str) -> None:
        if permission not in self.principal.permissions:
            raise PlatformAdminForbidden("PLATFORM_ADMIN_PERMISSION_DENIED")

    def dashboard(self) -> AdminDashboard:
        self.require("platform.read")
        return self.repository.dashboard()

    def failing_runs(self, *, limit: int = 100) -> tuple[SafeRunSummary, ...]:
        self.require("support.read")
        return self.repository.failing_runs(limit=limit)

    def dead_letters(self, *, limit: int = 100) -> tuple[SafeDeadLetter, ...]:
        self.require("platform.read")
        return self.repository.dead_letters(limit=limit)

    def replay_dead_letter(self, *, dead_letter_id: UUID, reason: str) -> None:
        self.require("queue.manage")
        reason = _reason(reason)
        if self.replay_port is None:
            raise PlatformAdminUnavailable("ADMIN_DLQ_REPLAY_ADAPTER_NOT_COMPOSED")
        material = self.repository.replay_material(dead_letter_id)
        self.replay_port.replay(material)
        self.repository.mark_replayed(dead_letter_id)
        self.repository.audit(
            principal=self.principal,
            action="dlq.replay",
            resource_type="dead_letter",
            resource_id=str(dead_letter_id),
            target_organization_id=material.organization_id,
            reason=reason,
            metadata={"replay_key": material.replay_key},
        )

    def discard_dead_letter(self, *, dead_letter_id: UUID, reason: str) -> None:
        self.require("queue.manage")
        reason = _reason(reason)
        material = self.repository.replay_material(dead_letter_id)
        self.repository.discard_dead_letter(dead_letter_id)
        self.repository.audit(
            principal=self.principal,
            action="dlq.discard",
            resource_type="dead_letter",
            resource_id=str(dead_letter_id),
            target_organization_id=material.organization_id,
            reason=reason,
        )

    def providers(self, *, limit: int = 100) -> tuple[ProviderControlSummary, ...]:
        self.require("provider.ops")
        return self.repository.provider_summaries(limit=limit)

    def provider_override(
        self,
        *,
        provider: str,
        model: str | None,
        capability: str | None,
        action: str,
        reason: str,
        expires_at: datetime | None = None,
    ) -> UUID:
        self.require(
            "provider.manage"
            if action in {"force_disabled", "clear_override"}
            else "provider.ops"
        )
        reason = _reason(reason)
        if capability is not None and model is None:
            raise ValueError("ADMIN_PROVIDER_CAPABILITY_REQUIRES_MODEL")
        if expires_at is not None and (
            expires_at.tzinfo is None or expires_at <= datetime.now(UTC)
        ):
            raise ValueError("ADMIN_PROVIDER_OVERRIDE_EXPIRY_INVALID")
        result = self.repository.provider_override(
            provider=provider,
            model=model,
            capability=capability,
            action=action,
            actor_user_id=self.principal.user_id,
            reason=reason,
            expires_at=expires_at,
        )
        self.repository.audit(
            principal=self.principal,
            action=f"provider.{action}",
            resource_type="provider",
            resource_id=provider,
            reason=reason,
            metadata={
                "model": model,
                "capability": capability,
                "expires_at": expires_at.isoformat() if expires_at else None,
            },
        )
        return result

    def feature_flags(self) -> tuple[FeatureFlag, ...]:
        self.require("platform.read")
        return self.repository.feature_flags()

    def upsert_feature_flag(
        self,
        *,
        flag_key: str,
        scope: str,
        target_id: str | None,
        value: dict[str, Any],
        owner: str,
        reason: str,
        security_locked: bool = False,
        expires_at: datetime | None = None,
    ) -> FeatureFlag:
        self.require("feature_flags.manage")
        reason = _reason(reason)
        if security_locked:
            raise PlatformAdminConflict(
                "ADMIN_SECURITY_FLAG_CREATION_REQUIRES_SECURITY_POLICY"
            )
        if scope not in {"global", "organization", "user"}:
            raise ValueError("ADMIN_FEATURE_FLAG_SCOPE_INVALID")
        if scope == "global" and target_id is not None:
            raise ValueError("ADMIN_GLOBAL_FLAG_TARGET_FORBIDDEN")
        if scope != "global" and not target_id:
            raise ValueError("ADMIN_SCOPED_FLAG_TARGET_REQUIRED")
        if expires_at is not None and (
            expires_at.tzinfo is None or expires_at <= datetime.now(UTC)
        ):
            raise ValueError("ADMIN_FEATURE_FLAG_EXPIRY_INVALID")
        flag = self.repository.upsert_feature_flag(
            actor_user_id=self.principal.user_id,
            flag_key=flag_key.strip(),
            scope=scope,
            target_id=target_id,
            value=value,
            owner=owner.strip(),
            reason=reason,
            security_locked=False,
            expires_at=expires_at,
        )
        self.repository.audit(
            principal=self.principal,
            action="feature_flag.upsert",
            resource_type="feature_flag",
            resource_id=str(flag.id),
            reason=reason,
            metadata={
                "flag_key": flag.flag_key,
                "scope": flag.scope,
                "target_id": flag.target_id,
            },
        )
        return flag

    def create_break_glass(
        self,
        *,
        scope: str,
        target_type: str,
        target_id: str,
        reason: str,
        ttl_minutes: int = 15,
    ) -> BreakGlassGrant:
        self.require("security.breakglass")
        reason = _reason(reason)
        if ttl_minutes < 1 or ttl_minutes > 30:
            raise ValueError("ADMIN_BREAK_GLASS_TTL_INVALID")
        expires_at = datetime.now(UTC) + timedelta(minutes=ttl_minutes)
        grant = self.repository.break_glass(
            actor_user_id=self.principal.user_id,
            scope=scope.strip(),
            target_type=target_type.strip(),
            target_id=target_id.strip(),
            reason=reason,
            expires_at=expires_at,
        )
        self.repository.audit(
            principal=self.principal,
            action="security.break_glass",
            resource_type=target_type,
            resource_id=target_id,
            reason=reason,
            metadata={"scope": scope, "expires_at": expires_at.isoformat()},
        )
        return grant

    def promote_registry_version(
        self, *, registry_kind: str, key: str, version: str, reason: str
    ) -> None:
        self.require("registry.promote")
        _reason(reason)
        raise PlatformAdminUnavailable("ADMIN_RELEASE_GATE_EVIDENCE_NOT_COMPOSED")


def _reason(value: str) -> str:
    normalized = value.strip()
    if len(normalized) < 8 or len(normalized) > 1000:
        raise ValueError("ADMIN_REASON_LENGTH_INVALID")
    return redact_audit_text(normalized)
