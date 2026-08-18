from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AdminModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PlatformAdminRole(StrEnum):
    SUPPORT_READ = "SUPPORT_READ"
    OPS = "OPS"
    BILLING_ADMIN = "BILLING_ADMIN"
    AI_CONFIG_ADMIN = "AI_CONFIG_ADMIN"
    SECURITY_ADMIN = "SECURITY_ADMIN"
    SUPER_ADMIN = "SUPER_ADMIN"


_ROLE_PERMISSIONS: dict[PlatformAdminRole, frozenset[str]] = {
    PlatformAdminRole.SUPPORT_READ: frozenset({"platform.read", "support.read"}),
    PlatformAdminRole.OPS: frozenset({"platform.read", "support.read", "queue.manage", "provider.ops", "incidents.manage"}),
    PlatformAdminRole.BILLING_ADMIN: frozenset({"platform.read", "support.read", "billing.admin"}),
    PlatformAdminRole.AI_CONFIG_ADMIN: frozenset({"platform.read", "provider.ops", "provider.manage", "registry.promote", "feature_flags.manage"}),
    PlatformAdminRole.SECURITY_ADMIN: frozenset({"platform.read", "support.read", "security.breakglass", "sessions.revoke", "admin_audit.read"}),
    PlatformAdminRole.SUPER_ADMIN: frozenset({"platform.read", "support.read", "queue.manage", "provider.ops", "provider.manage", "billing.admin", "registry.promote", "feature_flags.manage", "security.breakglass", "sessions.revoke", "admin_audit.read", "platform_admin.manage", "incidents.manage"}),
}


def role_permissions(role: PlatformAdminRole) -> tuple[str, ...]:
    return tuple(sorted(_ROLE_PERMISSIONS[role]))


class PlatformAdminError(RuntimeError):
    code = "PLATFORM_ADMIN_ERROR"


class PlatformAdminForbidden(PlatformAdminError):
    code = "PLATFORM_ADMIN_FORBIDDEN"


class PlatformAdminNotFound(PlatformAdminError):
    code = "PLATFORM_ADMIN_NOT_FOUND"


class PlatformAdminConflict(PlatformAdminError):
    code = "PLATFORM_ADMIN_CONFLICT"


class PlatformAdminUnavailable(PlatformAdminError):
    code = "PLATFORM_ADMIN_UNAVAILABLE"


class PlatformAdminPrincipal(AdminModel):
    id: UUID
    user_id: UUID
    role: PlatformAdminRole
    permissions: tuple[str, ...]
    active: bool


class AdminDashboard(AdminModel):
    active_runs: int = Field(ge=0)
    failed_runs: int = Field(ge=0)
    failed_tasks: int = Field(ge=0)
    queue_pending: int = Field(ge=0)
    dlq_open: int = Field(ge=0)
    degraded_providers: int = Field(ge=0)
    payment_events_pending: int = Field(ge=0)
    provider_cost_24h: str


class SafeRunSummary(AdminModel):
    id: UUID
    organization_id: UUID
    project_id: UUID
    status: str
    graph_key: str
    graph_version: str
    agent_config_version: str
    code_git_sha: str
    budget_amount: str
    budget_currency: str
    created_at: datetime
    updated_at: datetime


class SafeDeadLetter(AdminModel):
    id: UUID
    organization_id: UUID
    message_id: str
    message_kind: str
    source_queue: str
    consumer: str
    error_category: str
    error_code: str | None
    error_message: str
    attempts: int
    status: str
    failed_at: datetime
    last_failed_at: datetime
    replayed_at: datetime | None


class ProviderControlSummary(AdminModel):
    provider: str
    model: str | None
    capability: str | None
    state: str
    score: int
    observed_at: datetime
    override_action: str | None = None
    override_expires_at: datetime | None = None


class FeatureFlag(AdminModel):
    id: UUID
    flag_key: str
    scope: str
    target_id: str | None
    value: dict[str, Any]
    owner: str
    reason: str
    security_locked: bool
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class BreakGlassGrant(AdminModel):
    id: UUID
    actor_user_id: UUID
    scope: str
    target_type: str
    target_id: str
    reason: str
    expires_at: datetime
    created_at: datetime


class DeadLetterReplayRequest(AdminModel):
    replay_key: str
    dead_letter_id: UUID
    organization_id: UUID
    message_id: str
    message_kind: str
    source_queue: str
    exchange: str | None
    routing_key: str | None
    payload: dict[str, Any]
    traceparent: str | None


class DeadLetterReplayPort(Protocol):
    def replay(self, request: DeadLetterReplayRequest) -> None: ...
