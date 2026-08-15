from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol
from uuid import uuid4

from lumi_project_core.billing import BillingRepository, CreditLedgerEntry

AdminRole = Literal[
    "SUPPORT_READ",
    "SUPPORT_WRITE_LIMITED",
    "BILLING_ADMIN",
    "OPS",
    "MODEL_ADMIN",
    "SECURITY_AUDITOR",
    "PRIVACY_ADMIN",
]
ProviderHealth = Literal["HEALTHY", "DEGRADED", "UNAVAILABLE", "DISABLED"]
CircuitState = Literal["CLOSED", "OPEN", "HALF_OPEN"]
RegistryKind = Literal["AGENT", "SKILL"]

ROLE_PERMISSIONS: dict[AdminRole, frozenset[str]] = {
    "SUPPORT_READ": frozenset({"admin.user.read", "admin.provider.read", "admin.queue.read"}),
    "SUPPORT_WRITE_LIMITED": frozenset(
        {"admin.user.read", "admin.user.manage_limited", "admin.queue.read", "admin.queue.requeue"}
    ),
    "BILLING_ADMIN": frozenset({"admin.user.read", "admin.billing.read", "admin.billing.adjust"}),
    "OPS": frozenset(
        {
            "admin.user.read",
            "admin.user.manage_limited",
            "admin.provider.read",
            "admin.provider.manage",
            "admin.queue.read",
            "admin.queue.requeue",
        }
    ),
    "MODEL_ADMIN": frozenset(
        {
            "admin.provider.read",
            "admin.provider.manage",
            "admin.agent_registry.manage",
            "admin.skill_registry.manage",
        }
    ),
    "SECURITY_AUDITOR": frozenset({"admin.audit.read"}),
    "PRIVACY_ADMIN": frozenset({"admin.user.read", "admin.privacy.execute"}),
}


class AdminError(RuntimeError):
    def __init__(self, code: str, status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True, slots=True)
class PlatformAdminActor:
    actor_id: str
    roles: frozenset[AdminRole]
    permissions: frozenset[str]

    @classmethod
    def from_roles(cls, actor_id: str, roles: frozenset[AdminRole]) -> "PlatformAdminActor":
        if not actor_id.strip() or not roles:
            raise AdminError("ADMIN_ACTOR_INVALID", 401)
        permissions: set[str] = set()
        for role in roles:
            permissions.update(ROLE_PERMISSIONS[role])
        return cls(actor_id=actor_id, roles=roles, permissions=frozenset(permissions))


@dataclass(frozen=True, slots=True)
class SensitiveActionConfirmation:
    action_summary: str
    impact_scope: str
    reason: str
    ticket_ref: str
    confirmation: str

    def validate(self, *, expected_summary: str, expected_scope: str) -> None:
        if self.action_summary != expected_summary or self.impact_scope != expected_scope:
            raise AdminError("ADMIN_CONFIRMATION_SCOPE_MISMATCH", 409)
        if not self.reason.strip() or not self.ticket_ref.strip():
            raise AdminError("ADMIN_REASON_TICKET_REQUIRED")
        if self.confirmation != "CONFIRM":
            raise AdminError("ADMIN_SECOND_CONFIRMATION_REQUIRED", 409)


@dataclass(frozen=True, slots=True)
class SupportUser:
    user_id: str
    display_name: str
    email: str | None
    phone: str | None
    status: str
    organization_ids: tuple[str, ...]
    membership_roles: tuple[str, ...]
    recent_error_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SupportOrganization:
    organization_id: str
    name: str
    status: str


@dataclass(frozen=True, slots=True)
class SupportUserView:
    user_id: str
    display_name: str
    email_masked: str | None
    phone_masked: str | None
    status: str
    organization_ids: tuple[str, ...]
    membership_roles: tuple[str, ...]
    recent_error_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RevealedPii:
    user_id: str
    email: str | None
    phone: str | None


@dataclass(frozen=True, slots=True)
class AdminRunRecord:
    run_id: str
    organization_id: str
    task_id: str | None
    kind: Literal["GENERATION", "AGENT", "TOOL"]
    status: str
    provider: str | None
    tool: str | None
    error_code: str | None
    cost_microusd: int | None
    retryable: bool
    cancellable: bool
    created_at: str


@dataclass(frozen=True, slots=True)
class AdminProviderRecord:
    provider_id: str
    health: ProviderHealth
    circuit: CircuitState
    routing_weight_basis_points: int
    synthetic_health: ProviderHealth
    pricing_snapshot_id: str | None
    disabled_until: str | None = None
    disabled_reason: str | None = None


@dataclass(frozen=True, slots=True)
class AdminQueueRecord:
    queue_item_id: str
    task_id: str
    state: Literal["READY", "RUNNING", "STUCK", "DLQ"]
    payload_ref: str
    payload_sha256: str
    attempts: int
    last_error_code: str | None = None


@dataclass(frozen=True, slots=True)
class AdminRegistryEntry:
    registry_id: str
    kind: RegistryKind
    name: str
    version: str
    enabled: bool
    traffic_basis_points: int
    deploy_diff_summary: str


@dataclass(frozen=True, slots=True)
class AdminBillingView:
    organization_id: str
    plan_version_id: str | None
    subscription_state: str | None
    credit_balance: int
    invoice_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AdminOverview:
    active_users: int
    active_organizations: int
    daily_generations: int
    failure_rate_basis_points: int
    provider_health: ProviderHealth
    queue_depth: int
    cost_today_microusd: int | None
    critical_alerts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ViewAsSession:
    session_id: str
    admin_actor_id: str
    target_user_id: str
    target_organization_id: str
    readonly: bool
    started_at: str
    expires_at: str
    ended_at: str | None = None


@dataclass(frozen=True, slots=True)
class AdminAuditEvent:
    event_id: str
    event_type: str
    actor_id: str
    target_type: str
    target_id: str
    reason: str
    ticket_ref: str
    created_at: str
    safe_metadata: tuple[tuple[str, str], ...] = ()


class SupportDirectoryPort(Protocol):
    def list_users(self) -> tuple[SupportUser, ...]: ...
    def list_organizations(self) -> tuple[SupportOrganization, ...]: ...
    def get_user(self, user_id: str) -> SupportUser | None: ...


class RunOpsPort(Protocol):
    def list_runs(self) -> tuple[AdminRunRecord, ...]: ...
    def retry(self, run_id: str) -> AdminRunRecord: ...
    def cancel(self, run_id: str) -> AdminRunRecord: ...


class ProviderOpsPort(Protocol):
    def list_providers(self) -> tuple[AdminProviderRecord, ...]: ...
    def disable_temporarily(
        self, provider_id: str, *, expires_at: str, reason: str
    ) -> AdminProviderRecord: ...


class QueueOpsPort(Protocol):
    def list_queue(self) -> tuple[AdminQueueRecord, ...]: ...
    def requeue_original(
        self,
        queue_item_id: str,
        *,
        expected_payload_ref: str,
        expected_payload_sha256: str,
    ) -> AdminQueueRecord: ...


class RegistryOpsPort(Protocol):
    def list_registry(self) -> tuple[AdminRegistryEntry, ...]: ...
    def set_enabled(self, kind: RegistryKind, registry_id: str, enabled: bool) -> AdminRegistryEntry: ...


class CostOpsPort(Protocol):
    def cost_today_microusd(self) -> int | None: ...


class BillingAdminPort(Protocol):
    def summary(self, organization_id: str) -> AdminBillingView: ...
    def adjust_credits(
        self,
        *,
        organization_id: str,
        delta_credits: int,
        idempotency_key: str,
        source_id: str,
    ) -> AdminBillingView: ...


class ViewAsPort(Protocol):
    def get(self, session_id: str) -> ViewAsSession | None: ...
    def start(
        self,
        *,
        actor_id: str,
        target_user_id: str,
        target_organization_id: str,
        expires_at: str,
    ) -> ViewAsSession: ...
    def end(self, session_id: str) -> ViewAsSession: ...


class AdminAuditSink(Protocol):
    def emit(self, event: AdminAuditEvent) -> None: ...
    def recent(self) -> tuple[AdminAuditEvent, ...]: ...


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AdminError("ADMIN_TIME_INVALID") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def mask_email(value: str | None) -> str | None:
    if not value:
        return None
    local, sep, domain = value.partition("@")
    if not sep:
        return "••••"
    visible = local[:1] if local else ""
    return f"{visible}•••@{domain}"


def mask_phone(value: str | None) -> str | None:
    if not value:
        return None
    digits = "".join(char for char in value if char.isdigit())
    if len(digits) < 4:
        return "••••"
    return f"••••{digits[-4:]}"


class AdminConsoleService:
    def __init__(
        self,
        *,
        directory: SupportDirectoryPort,
        runs: RunOpsPort,
        providers: ProviderOpsPort,
        queue: QueueOpsPort,
        registry: RegistryOpsPort,
        costs: CostOpsPort,
        billing: BillingAdminPort,
        view_as: ViewAsPort,
        audit: AdminAuditSink,
    ) -> None:
        self._directory = directory
        self._runs = runs
        self._providers = providers
        self._queue = queue
        self._registry = registry
        self._costs = costs
        self._billing = billing
        self._view_as = view_as
        self._audit = audit

    def overview(self, actor: PlatformAdminActor) -> AdminOverview:
        self._require_any(
            actor,
            {
                "admin.user.read",
                "admin.provider.read",
                "admin.queue.read",
                "admin.billing.read",
                "admin.audit.read",
            },
        )
        users = self._directory.list_users()
        organizations = self._directory.list_organizations()
        runs = self._runs.list_runs()
        providers = self._providers.list_providers()
        queue = self._queue.list_queue()
        today = _now().date()
        today_runs = tuple(item for item in runs if _parse_time(item.created_at).date() == today)
        failures = sum(1 for item in today_runs if item.status in {"FAILED", "ERROR"})
        failure_rate = 0 if not today_runs else failures * 10_000 // len(today_runs)
        provider_health: ProviderHealth = "HEALTHY"
        if any(item.health in {"UNAVAILABLE", "DISABLED"} for item in providers):
            provider_health = "UNAVAILABLE"
        elif any(item.health == "DEGRADED" for item in providers):
            provider_health = "DEGRADED"
        alerts: list[str] = []
        if provider_health != "HEALTHY":
            alerts.append(f"PROVIDER_{provider_health}")
        if any(item.state == "DLQ" for item in queue):
            alerts.append("QUEUE_DLQ")
        if any(item.state == "STUCK" for item in queue):
            alerts.append("QUEUE_STUCK")
        if failure_rate >= 1_000:
            alerts.append("FAILURE_RATE_HIGH")
        return AdminOverview(
            active_users=sum(1 for item in users if item.status == "ACTIVE"),
            active_organizations=sum(1 for item in organizations if item.status == "ACTIVE"),
            daily_generations=sum(1 for item in today_runs if item.kind == "GENERATION"),
            failure_rate_basis_points=failure_rate,
            provider_health=provider_health,
            queue_depth=sum(1 for item in queue if item.state in {"READY", "RUNNING", "STUCK", "DLQ"}),
            cost_today_microusd=self._costs.cost_today_microusd(),
            critical_alerts=tuple(alerts),
        )

    def search_users(self, actor: PlatformAdminActor, query: str = "") -> tuple[SupportUserView, ...]:
        self._require(actor, "admin.user.read")
        needle = query.strip().lower()
        values = self._directory.list_users()
        if needle:
            values = tuple(
                item
                for item in values
                if needle in item.user_id.lower()
                or needle in item.display_name.lower()
                or any(needle in org.lower() for org in item.organization_ids)
            )
        return tuple(self._user_view(item) for item in values)

    def reveal_pii(
        self,
        actor: PlatformAdminActor,
        *,
        user_id: str,
        reason: str,
        ticket_ref: str,
    ) -> RevealedPii:
        self._require(actor, "admin.privacy.execute")
        if not reason.strip() or not ticket_ref.strip():
            raise AdminError("ADMIN_REASON_TICKET_REQUIRED")
        user = self._directory.get_user(user_id)
        if user is None:
            raise AdminError("ADMIN_USER_NOT_FOUND", 404)
        self._emit(
            actor,
            event_type="ADMIN_PII_REVEALED",
            target_type="USER",
            target_id=user_id,
            reason=reason,
            ticket_ref=ticket_ref,
            metadata=(("fields", "email,phone"),),
        )
        return RevealedPii(user_id=user.user_id, email=user.email, phone=user.phone)

    def search_runs(self, actor: PlatformAdminActor, query: str = "") -> tuple[AdminRunRecord, ...]:
        self._require(actor, "admin.user.read")
        needle = query.strip().lower()
        values = self._runs.list_runs()
        if not needle:
            return values
        return tuple(
            item
            for item in values
            if needle in item.run_id.lower()
            or needle in item.organization_id.lower()
            or (item.task_id is not None and needle in item.task_id.lower())
            or (item.error_code is not None and needle in item.error_code.lower())
        )

    def retry_run(
        self,
        actor: PlatformAdminActor,
        run_id: str,
        confirmation: SensitiveActionConfirmation,
    ) -> AdminRunRecord:
        self._require(actor, "admin.user.manage_limited")
        confirmation.validate(expected_summary=f"Retry run {run_id}", expected_scope=f"run:{run_id}")
        updated = self._runs.retry(run_id)
        self._emit_confirmed(actor, "ADMIN_RUN_RETRIED", "RUN", run_id, confirmation)
        return updated

    def cancel_run(
        self,
        actor: PlatformAdminActor,
        run_id: str,
        confirmation: SensitiveActionConfirmation,
    ) -> AdminRunRecord:
        self._require(actor, "admin.user.manage_limited")
        confirmation.validate(expected_summary=f"Cancel run {run_id}", expected_scope=f"run:{run_id}")
        updated = self._runs.cancel(run_id)
        self._emit_confirmed(actor, "ADMIN_RUN_CANCELLED", "RUN", run_id, confirmation)
        return updated

    def list_providers(self, actor: PlatformAdminActor) -> tuple[AdminProviderRecord, ...]:
        self._require(actor, "admin.provider.read")
        return self._providers.list_providers()

    def disable_provider_temporarily(
        self,
        actor: PlatformAdminActor,
        *,
        provider_id: str,
        expires_at: str,
        confirmation: SensitiveActionConfirmation,
    ) -> AdminProviderRecord:
        self._require(actor, "admin.provider.manage")
        confirmation.validate(
            expected_summary=f"Temporarily disable provider {provider_id}",
            expected_scope=f"provider:{provider_id}",
        )
        expiry = _parse_time(expires_at)
        now = _now()
        if expiry <= now or expiry > now + timedelta(hours=24):
            raise AdminError("ADMIN_PROVIDER_DISABLE_EXPIRY_INVALID")
        updated = self._providers.disable_temporarily(
            provider_id, expires_at=_iso(expiry), reason=confirmation.reason
        )
        self._emit_confirmed(
            actor,
            "ADMIN_PROVIDER_DISABLED",
            "PROVIDER",
            provider_id,
            confirmation,
            metadata=(("expires_at", _iso(expiry)),),
        )
        return updated

    def list_queue(self, actor: PlatformAdminActor) -> tuple[AdminQueueRecord, ...]:
        self._require(actor, "admin.queue.read")
        return self._queue.list_queue()

    def requeue(
        self,
        actor: PlatformAdminActor,
        *,
        queue_item_id: str,
        confirmation: SensitiveActionConfirmation,
    ) -> AdminQueueRecord:
        self._require(actor, "admin.queue.requeue")
        confirmation.validate(
            expected_summary=f"Requeue item {queue_item_id}",
            expected_scope=f"queue-item:{queue_item_id}",
        )
        before = next(
            (item for item in self._queue.list_queue() if item.queue_item_id == queue_item_id), None
        )
        if before is None:
            raise AdminError("ADMIN_QUEUE_ITEM_NOT_FOUND", 404)
        updated = self._queue.requeue_original(
            queue_item_id,
            expected_payload_ref=before.payload_ref,
            expected_payload_sha256=before.payload_sha256,
        )
        if updated.payload_ref != before.payload_ref or updated.payload_sha256 != before.payload_sha256:
            raise AdminError("ADMIN_QUEUE_PAYLOAD_MUTATED", 409)
        self._emit_confirmed(
            actor,
            "ADMIN_QUEUE_REQUEUED",
            "QUEUE_ITEM",
            queue_item_id,
            confirmation,
            metadata=(("payload_sha256", before.payload_sha256),),
        )
        return updated

    def list_registry(self, actor: PlatformAdminActor) -> tuple[AdminRegistryEntry, ...]:
        self._require_any(actor, {"admin.agent_registry.manage", "admin.skill_registry.manage"})
        return self._registry.list_registry()

    def set_registry_enabled(
        self,
        actor: PlatformAdminActor,
        *,
        kind: RegistryKind,
        registry_id: str,
        enabled: bool,
        confirmation: SensitiveActionConfirmation,
    ) -> AdminRegistryEntry:
        permission = "admin.agent_registry.manage" if kind == "AGENT" else "admin.skill_registry.manage"
        self._require(actor, permission)
        verb = "Enable" if enabled else "Disable"
        confirmation.validate(
            expected_summary=f"{verb} {kind.lower()} {registry_id}",
            expected_scope=f"{kind.lower()}:{registry_id}",
        )
        updated = self._registry.set_enabled(kind, registry_id, enabled)
        self._emit_confirmed(
            actor,
            "ADMIN_REGISTRY_CHANGED",
            kind,
            registry_id,
            confirmation,
            metadata=(("enabled", str(enabled).lower()), ("version", updated.version)),
        )
        return updated

    def billing_summary(self, actor: PlatformAdminActor, organization_id: str) -> AdminBillingView:
        self._require(actor, "admin.billing.read")
        return self._billing.summary(organization_id)

    def adjust_billing(
        self,
        actor: PlatformAdminActor,
        *,
        organization_id: str,
        delta_credits: int,
        idempotency_key: str,
        confirmation: SensitiveActionConfirmation,
    ) -> AdminBillingView:
        self._require(actor, "admin.billing.adjust")
        if delta_credits == 0 or not idempotency_key.strip():
            raise AdminError("ADMIN_BILLING_ADJUSTMENT_INVALID")
        confirmation.validate(
            expected_summary=f"Adjust billing credits by {delta_credits}",
            expected_scope=f"organization:{organization_id}",
        )
        view = self._billing.adjust_credits(
            organization_id=organization_id,
            delta_credits=delta_credits,
            idempotency_key=idempotency_key,
            source_id=f"admin:{actor.actor_id}:{confirmation.ticket_ref}",
        )
        self._emit_confirmed(
            actor,
            "ADMIN_BILLING_ADJUSTED",
            "ORGANIZATION",
            organization_id,
            confirmation,
            metadata=(("delta_credits", str(delta_credits)),),
        )
        return view

    def start_view_as(
        self,
        actor: PlatformAdminActor,
        *,
        target_user_id: str,
        target_organization_id: str,
        reason: str,
        ticket_ref: str,
        ttl_minutes: int = 10,
    ) -> ViewAsSession:
        self._require(actor, "admin.user.read")
        if not reason.strip() or not ticket_ref.strip() or ttl_minutes < 1 or ttl_minutes > 15:
            raise AdminError("ADMIN_VIEW_AS_INVALID")
        user = self._directory.get_user(target_user_id)
        if user is None or target_organization_id not in user.organization_ids:
            raise AdminError("ADMIN_VIEW_AS_TARGET_INVALID", 404)
        session = self._view_as.start(
            actor_id=actor.actor_id,
            target_user_id=target_user_id,
            target_organization_id=target_organization_id,
            expires_at=_iso(_now() + timedelta(minutes=ttl_minutes)),
        )
        if not session.readonly:
            raise AdminError("ADMIN_VIEW_AS_MUST_BE_READONLY", 409)
        self._emit(
            actor,
            event_type="ADMIN_VIEW_AS_STARTED",
            target_type="USER",
            target_id=target_user_id,
            reason=reason,
            ticket_ref=ticket_ref,
            metadata=(("organization_id", target_organization_id), ("session_id", session.session_id)),
        )
        return session

    def end_view_as(
        self,
        actor: PlatformAdminActor,
        *,
        session_id: str,
        reason: str,
        ticket_ref: str,
    ) -> ViewAsSession:
        self._require(actor, "admin.user.read")
        if not reason.strip() or not ticket_ref.strip():
            raise AdminError("ADMIN_REASON_TICKET_REQUIRED")
        current = self._view_as.get(session_id)
        if current is None:
            raise AdminError("ADMIN_VIEW_AS_NOT_FOUND", 404)
        if current.admin_actor_id != actor.actor_id:
            raise AdminError("ADMIN_VIEW_AS_OWNER_MISMATCH", 403)
        session = self._view_as.end(session_id)
        self._emit(
            actor,
            event_type="ADMIN_VIEW_AS_ENDED",
            target_type="VIEW_AS_SESSION",
            target_id=session_id,
            reason=reason,
            ticket_ref=ticket_ref,
        )
        return session

    def recent_audit(self, actor: PlatformAdminActor) -> tuple[AdminAuditEvent, ...]:
        self._require(actor, "admin.audit.read")
        return self._audit.recent()

    @staticmethod
    def _user_view(user: SupportUser) -> SupportUserView:
        return SupportUserView(
            user_id=user.user_id,
            display_name=user.display_name,
            email_masked=mask_email(user.email),
            phone_masked=mask_phone(user.phone),
            status=user.status,
            organization_ids=user.organization_ids,
            membership_roles=user.membership_roles,
            recent_error_codes=user.recent_error_codes,
        )

    @staticmethod
    def _require(actor: PlatformAdminActor, permission: str) -> None:
        if permission not in actor.permissions:
            raise AdminError("ADMIN_FORBIDDEN", 403)

    @staticmethod
    def _require_any(actor: PlatformAdminActor, permissions: set[str]) -> None:
        if not actor.permissions.intersection(permissions):
            raise AdminError("ADMIN_FORBIDDEN", 403)

    def _emit_confirmed(
        self,
        actor: PlatformAdminActor,
        event_type: str,
        target_type: str,
        target_id: str,
        confirmation: SensitiveActionConfirmation,
        metadata: tuple[tuple[str, str], ...] = (),
    ) -> None:
        self._emit(
            actor,
            event_type=event_type,
            target_type=target_type,
            target_id=target_id,
            reason=confirmation.reason,
            ticket_ref=confirmation.ticket_ref,
            metadata=metadata,
        )

    def _emit(
        self,
        actor: PlatformAdminActor,
        *,
        event_type: str,
        target_type: str,
        target_id: str,
        reason: str,
        ticket_ref: str,
        metadata: tuple[tuple[str, str], ...] = (),
    ) -> None:
        self._audit.emit(
            AdminAuditEvent(
                event_id=str(uuid4()),
                event_type=event_type,
                actor_id=actor.actor_id,
                target_type=target_type,
                target_id=target_id,
                reason=reason,
                ticket_ref=ticket_ref,
                created_at=_iso(_now()),
                safe_metadata=metadata,
            )
        )


class Node63CreditLedgerAdapter:
    """Privileged service adapter that writes only NODE-63 immutable credit entries."""

    def __init__(self, repository: BillingRepository) -> None:
        self._repository = repository

    def summary(self, organization_id: str) -> AdminBillingView:
        subscription = self._repository.get_subscription(organization_id)
        return AdminBillingView(
            organization_id=organization_id,
            plan_version_id=subscription.plan_version_id if subscription else None,
            subscription_state=subscription.state if subscription else None,
            credit_balance=self._repository.credit_balance(organization_id),
            invoice_refs=tuple(
                item.provider_invoice_ref for item in self._repository.list_invoices(organization_id)
            ),
        )

    def adjust_credits(
        self,
        *,
        organization_id: str,
        delta_credits: int,
        idempotency_key: str,
        source_id: str,
    ) -> AdminBillingView:
        if delta_credits == 0:
            raise AdminError("ADMIN_BILLING_ADJUSTMENT_INVALID")
        prior = self._repository.append_credit(
            CreditLedgerEntry(
                entry_id=str(uuid4()),
                organization_id=organization_id,
                entry_type="ADJUSTMENT",
                delta_credits=delta_credits,
                source_type="ADMIN_ADJUSTMENT",
                source_id=source_id,
                pricing_policy_version=None,
                idempotency_key=idempotency_key,
                created_at=_iso(_now()),
            ),
            require_non_negative=delta_credits < 0,
        )
        if prior.source_id != source_id or prior.delta_credits != delta_credits:
            raise AdminError("ADMIN_BILLING_IDEMPOTENCY_KEY_REUSED", 409)
        return self.summary(organization_id)


class InMemoryAdminAuditSink:
    def __init__(self) -> None:
        self.events: list[AdminAuditEvent] = []

    def emit(self, event: AdminAuditEvent) -> None:
        self.events.append(event)

    def recent(self) -> tuple[AdminAuditEvent, ...]:
        return tuple(reversed(self.events[-100:]))


class InMemoryViewAsStore:
    def __init__(self) -> None:
        self.sessions: dict[str, ViewAsSession] = {}

    def get(self, session_id: str) -> ViewAsSession | None:
        return self.sessions.get(session_id)

    def start(
        self,
        *,
        actor_id: str,
        target_user_id: str,
        target_organization_id: str,
        expires_at: str,
    ) -> ViewAsSession:
        session = ViewAsSession(
            session_id=f"view-{uuid4()}",
            admin_actor_id=actor_id,
            target_user_id=target_user_id,
            target_organization_id=target_organization_id,
            readonly=True,
            started_at=_iso(_now()),
            expires_at=expires_at,
        )
        self.sessions[session.session_id] = session
        return session

    def end(self, session_id: str) -> ViewAsSession:
        current = self.sessions.get(session_id)
        if current is None:
            raise AdminError("ADMIN_VIEW_AS_NOT_FOUND", 404)
        if current.ended_at is not None:
            return current
        updated = replace(current, ended_at=_iso(_now()))
        self.sessions[session_id] = updated
        return updated
