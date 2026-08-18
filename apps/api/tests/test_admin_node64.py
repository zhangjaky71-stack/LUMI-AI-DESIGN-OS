from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from lumi_api.admin import (
    BreakGlassGrant,
    DeadLetterReplayRequest,
    FeatureFlag,
    PlatformAdminConflict,
    PlatformAdminForbidden,
    PlatformAdminPrincipal,
    PlatformAdminRole,
    PlatformAdminService,
    PlatformAdminUnavailable,
    role_permissions,
)

ROOT = Path(__file__).resolve().parents[3]


def _principal(role: PlatformAdminRole) -> PlatformAdminPrincipal:
    return PlatformAdminPrincipal(
        id=uuid4(),
        user_id=uuid4(),
        role=role,
        permissions=role_permissions(role),
        active=True,
    )


class FakeReplayPort:
    def __init__(self) -> None:
        self.requests: list[DeadLetterReplayRequest] = []

    def replay(self, request: DeadLetterReplayRequest) -> None:
        self.requests.append(request)


class FakeRepository:
    def __init__(self) -> None:
        self.organization_id = uuid4()
        self.dead_letter_id = uuid4()
        self.audits: list[dict[str, object]] = []
        self.replayed: list[UUID] = []
        self.discarded: list[UUID] = []
        self.provider_actions: list[str] = []
        self.flags: list[FeatureFlag] = []
        self.break_glass_grants: list[BreakGlassGrant] = []

    def replay_material(self, dead_letter_id: UUID) -> DeadLetterReplayRequest:
        assert dead_letter_id == self.dead_letter_id
        return DeadLetterReplayRequest(
            replay_key=f"admin-dlq-replay:{dead_letter_id}",
            dead_letter_id=dead_letter_id,
            organization_id=self.organization_id,
            message_id=str(uuid4()),
            message_kind="job",
            source_queue="lumi.jobs",
            exchange="lumi",
            routing_key="job.retry",
            payload={"safe": "fixture"},
            traceparent=None,
        )

    def mark_replayed(self, dead_letter_id: UUID) -> None:
        self.replayed.append(dead_letter_id)

    def discard_dead_letter(self, dead_letter_id: UUID) -> None:
        self.discarded.append(dead_letter_id)

    def audit(self, **kwargs: object) -> None:
        self.audits.append(dict(kwargs))

    def provider_override(
        self,
        *,
        provider: str,
        model: str | None,
        capability: str | None,
        action: str,
        actor_user_id: UUID,
        reason: str,
        expires_at: datetime | None,
    ) -> UUID:
        del provider, model, capability, actor_user_id, reason, expires_at
        self.provider_actions.append(action)
        return uuid4()

    def upsert_feature_flag(
        self,
        *,
        actor_user_id: UUID,
        flag_key: str,
        scope: str,
        target_id: str | None,
        value: dict[str, object],
        owner: str,
        reason: str,
        expires_at: datetime | None,
    ) -> FeatureFlag:
        now = datetime.now(UTC)
        flag = FeatureFlag(
            id=uuid4(),
            flag_key=flag_key,
            scope=scope,
            target_id=target_id,
            value=value,
            owner=owner,
            reason=reason,
            security_locked=False,
            expires_at=expires_at,
            created_at=now,
            updated_at=now,
        )
        self.flags.append(flag)
        return flag

    def break_glass(
        self,
        *,
        actor_user_id: UUID,
        scope: str,
        target_type: str,
        target_id: str,
        reason: str,
        expires_at: datetime,
    ) -> BreakGlassGrant:
        grant = BreakGlassGrant(
            id=uuid4(),
            actor_user_id=actor_user_id,
            scope=scope,
            target_type=target_type,
            target_id=target_id,
            reason=reason,
            expires_at=expires_at,
            created_at=datetime.now(UTC),
        )
        self.break_glass_grants.append(grant)
        return grant


def test_platform_admin_roles_are_separate_from_organization_owner() -> None:
    roles = {role.value for role in PlatformAdminRole}
    assert "OWNER" not in roles
    assert "ADMIN" not in roles
    assert "SUPER_ADMIN" in roles

    factory_source = (ROOT / "apps/api/src/lumi_api/admin/factory.py").read_text()
    auth_guard = (ROOT / "apps/api/src/lumi_api/api/v1/admin_auth_guard.py").read_text()
    assert "principal_for_user" in factory_source
    assert "PLATFORM_ADMIN_PRINCIPAL_REQUIRED" in factory_source
    assert "organization owner" not in factory_source.casefold()
    assert "platform_admin_user_id" in auth_guard


def test_permission_matrix_does_not_collapse_high_risk_roles() -> None:
    ops = set(role_permissions(PlatformAdminRole.OPS))
    ai = set(role_permissions(PlatformAdminRole.AI_CONFIG_ADMIN))
    billing = set(role_permissions(PlatformAdminRole.BILLING_ADMIN))
    security = set(role_permissions(PlatformAdminRole.SECURITY_ADMIN))

    assert "queue.manage" in ops
    assert "provider.ops" in ops
    assert "provider.manage" not in ops
    assert "provider.manage" in ai
    assert "registry.promote" in ai
    assert "billing.admin" in billing
    assert "security.breakglass" in security
    assert "billing.admin" not in security


def test_dlq_replay_requires_ops_permission_and_audits() -> None:
    repo = FakeRepository()
    replay = FakeReplayPort()
    support = PlatformAdminService(repo, _principal(PlatformAdminRole.SUPPORT_READ), replay)  # type: ignore[arg-type]
    with pytest.raises(PlatformAdminForbidden, match="PERMISSION_DENIED"):
        support.replay_dead_letter(
            dead_letter_id=repo.dead_letter_id,
            reason="Support cannot replay production work",
        )

    ops = PlatformAdminService(repo, _principal(PlatformAdminRole.OPS), replay)  # type: ignore[arg-type]
    ops.replay_dead_letter(
        dead_letter_id=repo.dead_letter_id,
        reason="Retry after transient provider recovery",
    )
    assert len(replay.requests) == 1
    assert replay.requests[0].replay_key == f"admin-dlq-replay:{repo.dead_letter_id}"
    assert repo.replayed == [repo.dead_letter_id]
    assert repo.audits[-1]["action"] == "dlq.replay"
    assert repo.audits[-1]["reason"] == "Retry after transient provider recovery"


def test_provider_disable_is_reserved_for_ai_config_admin() -> None:
    repo = FakeRepository()
    ops = PlatformAdminService(repo, _principal(PlatformAdminRole.OPS))  # type: ignore[arg-type]
    with pytest.raises(PlatformAdminForbidden, match="PERMISSION_DENIED"):
        ops.provider_override(
            provider="openai",
            model=None,
            capability=None,
            action="force_disabled",
            reason="Disable provider during confirmed incident",
        )

    ai = PlatformAdminService(repo, _principal(PlatformAdminRole.AI_CONFIG_ADMIN))  # type: ignore[arg-type]
    ai.provider_override(
        provider="openai",
        model=None,
        capability=None,
        action="force_disabled",
        reason="Disable provider during confirmed incident",
    )
    assert repo.provider_actions == ["force_disabled"]
    assert repo.audits[-1]["action"] == "provider.force_disabled"


def test_registry_promotion_fails_closed_without_release_gate_evidence() -> None:
    service = PlatformAdminService(
        FakeRepository(),  # type: ignore[arg-type]
        _principal(PlatformAdminRole.AI_CONFIG_ADMIN),
    )
    with pytest.raises(PlatformAdminUnavailable, match="RELEASE_GATE_EVIDENCE_NOT_COMPOSED"):
        service.promote_registry_version(
            registry_kind="agent",
            key="lumi.main",
            version="2026.08.18",
            reason="Promote only after release gate passes",
        )


def test_break_glass_is_short_lived_and_audited() -> None:
    repo = FakeRepository()
    service = PlatformAdminService(repo, _principal(PlatformAdminRole.SECURITY_ADMIN))  # type: ignore[arg-type]
    before = datetime.now(UTC)
    grant = service.create_break_glass(
        scope="artifact.private.read",
        target_type="artifact",
        target_id=str(uuid4()),
        reason="Investigate customer-reported corrupted export",
        ttl_minutes=15,
    )
    assert before + timedelta(minutes=14) < grant.expires_at <= before + timedelta(minutes=16)
    assert repo.audits[-1]["action"] == "security.break_glass"

    with pytest.raises(ValueError, match="TTL_INVALID"):
        service.create_break_glass(
            scope="artifact.private.read",
            target_type="artifact",
            target_id=str(uuid4()),
            reason="Investigate customer-reported corrupted export",
            ttl_minutes=31,
        )


def test_feature_flags_require_scope_and_future_expiry() -> None:
    repo = FakeRepository()
    service = PlatformAdminService(repo, _principal(PlatformAdminRole.AI_CONFIG_ADMIN))  # type: ignore[arg-type]
    expires = datetime.now(UTC) + timedelta(hours=1)
    flag = service.upsert_feature_flag(
        flag_key="generation.new_router",
        scope="organization",
        target_id=str(uuid4()),
        value={"enabled": True},
        owner="model-platform",
        reason="Controlled organization canary rollout",
        expires_at=expires,
    )
    assert flag.expires_at == expires
    assert repo.audits[-1]["action"] == "feature_flag.upsert"

    with pytest.raises(ValueError, match="TARGET_REQUIRED"):
        service.upsert_feature_flag(
            flag_key="generation.new_router",
            scope="organization",
            target_id=None,
            value={"enabled": True},
            owner="model-platform",
            reason="Controlled organization canary rollout",
        )
    with pytest.raises(PlatformAdminConflict, match="SECURITY_FLAG_CREATION"):
        service.upsert_feature_flag(
            flag_key="security.disable_auth",
            scope="global",
            target_id=None,
            value={"enabled": True},
            owner="security",
            reason="Security controls cannot be ordinary flags",
            security_locked=True,
        )


def test_safe_admin_contracts_do_not_expose_secret_or_private_payloads() -> None:
    contracts = (ROOT / "apps/api/src/lumi_api/admin/contracts.py").read_text()
    routes = (ROOT / "apps/api/src/lumi_api/api/v1/admin_routes.py").read_text()
    migration = (
        ROOT / "apps/api/migrations/versions/20260818_0024_sql/up.sql"
    ).read_text()

    safe_run_block = contracts.split("class SafeRunSummary", 1)[1].split("class SafeDeadLetter", 1)[0]
    safe_dlq_block = contracts.split("class SafeDeadLetter", 1)[1].split("class ProviderControlSummary", 1)[0]
    assert "input_json" not in safe_run_block
    assert "output_json" not in safe_run_block
    assert "payload" not in safe_dlq_block
    assert "secret" not in routes.casefold()
    assert "token" not in routes.casefold()
    assert "trg_platform_admin_audit_immutable" in migration
    assert "trg_platform_break_glass_immutable" in migration
