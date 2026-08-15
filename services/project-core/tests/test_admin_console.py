from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from lumi_project_core.admin_console import (
    AdminBillingView,
    AdminConsoleService,
    AdminError,
    AdminProviderRecord,
    AdminQueueRecord,
    AdminRegistryEntry,
    AdminRunRecord,
    InMemoryAdminAuditSink,
    InMemoryViewAsStore,
    Node63CreditLedgerAdapter,
    PlatformAdminActor,
    SensitiveActionConfirmation,
    SupportOrganization,
    SupportUser,
)
from lumi_project_core.billing import (
    BillingError,
    CreditLedgerEntry,
    InMemoryBillingRepository,
)


class Directory:
    def __init__(self) -> None:
        self.users = (
            SupportUser(
                user_id="user-1",
                display_name="Ada Operator",
                email="ada@example.test",
                phone="+81 90 1234 5678",
                status="ACTIVE",
                organization_ids=("org-a",),
                membership_roles=("OWNER",),
                recent_error_codes=("MODEL_TIMEOUT",),
            ),
        )
        self.organizations = (SupportOrganization("org-a", "Alpha", "ACTIVE"),)

    def list_users(self):
        return self.users

    def list_organizations(self):
        return self.organizations

    def get_user(self, user_id: str):
        return next((item for item in self.users if item.user_id == user_id), None)


class Runs:
    def __init__(self) -> None:
        self.items = {
            "run-1": AdminRunRecord(
                run_id="run-1",
                organization_id="org-a",
                task_id="task-1",
                kind="GENERATION",
                status="FAILED",
                provider="mock-image",
                tool=None,
                error_code="MODEL_TIMEOUT",
                cost_microusd=12_000,
                retryable=True,
                cancellable=False,
                created_at=datetime.now(UTC).isoformat(),
            ),
            "run-2": AdminRunRecord(
                run_id="run-2",
                organization_id="org-a",
                task_id="task-2",
                kind="AGENT",
                status="RUNNING",
                provider="reasoning-primary",
                tool=None,
                error_code=None,
                cost_microusd=6_000,
                retryable=False,
                cancellable=True,
                created_at=datetime.now(UTC).isoformat(),
            ),
        }

    def list_runs(self):
        return tuple(self.items.values())

    def retry(self, run_id: str):
        current = self.items[run_id]
        if not current.retryable:
            raise AdminError("ADMIN_RUN_NOT_RETRYABLE", 409)
        updated = replace(current, status="QUEUED", retryable=False)
        self.items[run_id] = updated
        return updated

    def cancel(self, run_id: str):
        current = self.items[run_id]
        if not current.cancellable:
            raise AdminError("ADMIN_RUN_NOT_CANCELLABLE", 409)
        updated = replace(current, status="CANCELLED", cancellable=False)
        self.items[run_id] = updated
        return updated


class Providers:
    def __init__(self) -> None:
        self.items = {
            "mock-image": AdminProviderRecord(
                provider_id="mock-image",
                health="DEGRADED",
                circuit="CLOSED",
                routing_weight_basis_points=10_000,
                synthetic_health="HEALTHY",
                pricing_snapshot_id="pricing-v4",
            )
        }

    def list_providers(self):
        return tuple(self.items.values())

    def disable_temporarily(self, provider_id: str, *, expires_at: str, reason: str):
        current = self.items[provider_id]
        updated = replace(
            current,
            health="DISABLED",
            routing_weight_basis_points=0,
            disabled_until=expires_at,
            disabled_reason=reason,
        )
        self.items[provider_id] = updated
        return updated


class Queue:
    def __init__(self) -> None:
        self.items = {
            "queue-1": AdminQueueRecord(
                queue_item_id="queue-1",
                task_id="task-1",
                state="DLQ",
                payload_ref="payload://immutable/task-1/v1",
                payload_sha256="a" * 64,
                attempts=3,
                last_error_code="PROVIDER_UNAVAILABLE",
            )
        }
        self.expected = None

    def list_queue(self):
        return tuple(self.items.values())

    def requeue_original(
        self,
        queue_item_id: str,
        *,
        expected_payload_ref: str,
        expected_payload_sha256: str,
    ):
        current = self.items[queue_item_id]
        self.expected = (expected_payload_ref, expected_payload_sha256)
        if (
            current.payload_ref != expected_payload_ref
            or current.payload_sha256 != expected_payload_sha256
        ):
            raise AdminError("ADMIN_QUEUE_PAYLOAD_CONFLICT", 409)
        updated = replace(current, state="READY", attempts=current.attempts + 1)
        self.items[queue_item_id] = updated
        return updated


class Registry:
    def __init__(self) -> None:
        self.items = {
            ("AGENT", "designer"): AdminRegistryEntry(
                registry_id="designer",
                kind="AGENT",
                name="Designer Agent",
                version="v7",
                enabled=True,
                traffic_basis_points=10_000,
                deploy_diff_summary="prompt bundle v7; tools unchanged",
            )
        }

    def list_registry(self):
        return tuple(self.items.values())

    def set_enabled(self, kind, registry_id: str, enabled: bool):
        current = self.items[(kind, registry_id)]
        updated = replace(current, enabled=enabled)
        self.items[(kind, registry_id)] = updated
        return updated


class Costs:
    def cost_today_microusd(self):
        return 143_200


class Billing:
    def __init__(self) -> None:
        self.value = AdminBillingView("org-a", "pro-v2", "ACTIVE", 1200, ("in-42",))

    def summary(self, organization_id: str):
        assert organization_id == "org-a"
        return self.value

    def adjust_credits(
        self,
        *,
        organization_id: str,
        delta_credits: int,
        idempotency_key: str,
        source_id: str,
    ):
        assert organization_id == "org-a"
        assert idempotency_key
        assert source_id.startswith("admin:")
        self.value = replace(
            self.value,
            credit_balance=self.value.credit_balance + delta_credits,
        )
        return self.value


def confirm(summary: str, scope: str) -> SensitiveActionConfirmation:
    return SensitiveActionConfirmation(
        summary,
        scope,
        "incident mitigation",
        "INC-6401",
        "CONFIRM",
    )


def make_service(*, billing=None):
    audit = InMemoryAdminAuditSink()
    queue = Queue()
    return (
        AdminConsoleService(
            directory=Directory(),
            runs=Runs(),
            providers=Providers(),
            queue=queue,
            registry=Registry(),
            costs=Costs(),
            billing=billing or Billing(),
            view_as=InMemoryViewAsStore(),
            audit=audit,
        ),
        audit,
        queue,
    )


def test_platform_admin_role_is_separate_and_rbac_fails_closed():
    actor = PlatformAdminActor.from_roles("support-1", frozenset({"SUPPORT_READ"}))
    service, _, _ = make_service()
    assert not hasattr(actor, "organization_id")
    with pytest.raises(AdminError, match="ADMIN_FORBIDDEN"):
        service.disable_provider_temporarily(
            actor,
            provider_id="mock-image",
            expires_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            confirmation=confirm(
                "Temporarily disable provider mock-image",
                "provider:mock-image",
            ),
        )


def test_support_search_masks_pii_by_default_and_reveal_requires_privacy_permission():
    service, audit, _ = make_service()
    support = PlatformAdminActor.from_roles("support-1", frozenset({"SUPPORT_READ"}))
    row = service.search_users(support)[0]
    assert row.email_masked == "a•••@example.test"
    assert row.phone_masked == "••••5678"
    assert "ada@example.test" not in repr(row)
    with pytest.raises(AdminError, match="ADMIN_FORBIDDEN"):
        service.reveal_pii(
            support,
            user_id="user-1",
            reason="case",
            ticket_ref="SUP-1",
        )

    privacy = PlatformAdminActor.from_roles(
        "privacy-1",
        frozenset({"PRIVACY_ADMIN"}),
    )
    revealed = service.reveal_pii(
        privacy,
        user_id="user-1",
        reason="customer request",
        ticket_ref="PRIV-9",
    )
    assert revealed.email == "ada@example.test"
    assert audit.events[-1].event_type == "ADMIN_PII_REVEALED"
    assert "ada@example.test" not in repr(audit.events[-1])


def test_provider_disable_requires_exact_second_confirmation_and_bounded_expiry():
    service, audit, _ = make_service()
    actor = PlatformAdminActor.from_roles("ops-1", frozenset({"OPS"}))
    bad = SensitiveActionConfirmation(
        "Temporarily disable provider mock-image",
        "provider:mock-image",
        "incident",
        "INC-1",
        "NO",
    )
    with pytest.raises(AdminError, match="ADMIN_SECOND_CONFIRMATION_REQUIRED"):
        service.disable_provider_temporarily(
            actor,
            provider_id="mock-image",
            expires_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            confirmation=bad,
        )
    with pytest.raises(AdminError, match="ADMIN_PROVIDER_DISABLE_EXPIRY_INVALID"):
        service.disable_provider_temporarily(
            actor,
            provider_id="mock-image",
            expires_at=(datetime.now(UTC) + timedelta(days=2)).isoformat(),
            confirmation=confirm(
                "Temporarily disable provider mock-image",
                "provider:mock-image",
            ),
        )
    updated = service.disable_provider_temporarily(
        actor,
        provider_id="mock-image",
        expires_at=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        confirmation=confirm(
            "Temporarily disable provider mock-image",
            "provider:mock-image",
        ),
    )
    assert updated.health == "DISABLED"
    assert updated.routing_weight_basis_points == 0
    assert audit.events[-1].event_type == "ADMIN_PROVIDER_DISABLED"


def test_run_retry_and_cancel_use_distinct_guarded_service_operations():
    service, audit, _ = make_service()
    actor = PlatformAdminActor.from_roles("ops-1", frozenset({"OPS"}))
    retried = service.retry_run(
        actor,
        "run-1",
        confirm("Retry run run-1", "run:run-1"),
    )
    cancelled = service.cancel_run(
        actor,
        "run-2",
        confirm("Cancel run run-2", "run:run-2"),
    )
    assert retried.status == "QUEUED"
    assert cancelled.status == "CANCELLED"
    assert [event.event_type for event in audit.events[-2:]] == [
        "ADMIN_RUN_RETRIED",
        "ADMIN_RUN_CANCELLED",
    ]


def test_requeue_reuses_original_immutable_payload_and_audits():
    service, audit, queue = make_service()
    actor = PlatformAdminActor.from_roles("ops-1", frozenset({"OPS"}))
    before = service.list_queue(actor)[0]
    updated = service.requeue(
        actor,
        queue_item_id="queue-1",
        confirmation=confirm("Requeue item queue-1", "queue-item:queue-1"),
    )
    assert updated.state == "READY"
    assert updated.payload_ref == before.payload_ref
    assert updated.payload_sha256 == before.payload_sha256
    assert queue.expected == (before.payload_ref, before.payload_sha256)
    assert audit.events[-1].event_type == "ADMIN_QUEUE_REQUEUED"


def test_billing_adjustment_uses_node63_immutable_adjustment_ledger():
    repository = InMemoryBillingRepository()
    repository.append_credit(
        CreditLedgerEntry(
            entry_id="grant-1",
            organization_id="org-a",
            entry_type="GRANT",
            delta_credits=100,
            source_type="SEED",
            source_id="seed",
            pricing_policy_version=None,
            idempotency_key="seed-1",
            created_at=datetime.now(UTC).isoformat(),
        )
    )
    adapter = Node63CreditLedgerAdapter(repository)
    service, audit, _ = make_service(billing=adapter)
    actor = PlatformAdminActor.from_roles("billing-1", frozenset({"BILLING_ADMIN"}))
    view = service.adjust_billing(
        actor,
        organization_id="org-a",
        delta_credits=25,
        idempotency_key="adjust-6401",
        confirmation=confirm(
            "Adjust billing credits by 25",
            "organization:org-a",
        ),
    )
    assert view.credit_balance == 125
    ledger = repository.list_credit_entries("org-a")
    assert ledger[0].entry_type == "ADJUSTMENT"
    assert ledger[0].delta_credits == 25
    assert ledger[1].entry_type == "GRANT"
    assert audit.events[-1].event_type == "ADMIN_BILLING_ADJUSTED"


def test_negative_billing_adjustment_cannot_create_negative_balance():
    repository = InMemoryBillingRepository()
    adapter = Node63CreditLedgerAdapter(repository)
    service, _, _ = make_service(billing=adapter)
    actor = PlatformAdminActor.from_roles("billing-1", frozenset({"BILLING_ADMIN"}))
    with pytest.raises(BillingError, match="BILLING_INSUFFICIENT_CREDITS"):
        service.adjust_billing(
            actor,
            organization_id="org-a",
            delta_credits=-1,
            idempotency_key="adjust-negative",
            confirmation=confirm(
                "Adjust billing credits by -1",
                "organization:org-a",
            ),
        )


def test_view_as_is_readonly_short_lived_and_owner_scoped():
    service, audit, _ = make_service()
    actor = PlatformAdminActor.from_roles("support-1", frozenset({"SUPPORT_READ"}))
    session = service.start_view_as(
        actor,
        target_user_id="user-1",
        target_organization_id="org-a",
        reason="reproduce customer view",
        ticket_ref="SUP-64",
        ttl_minutes=5,
    )
    assert session.readonly is True
    assert datetime.fromisoformat(session.expires_at) - datetime.fromisoformat(
        session.started_at
    ) <= timedelta(minutes=6)
    other = PlatformAdminActor.from_roles("support-2", frozenset({"SUPPORT_READ"}))
    with pytest.raises(AdminError, match="ADMIN_VIEW_AS_OWNER_MISMATCH"):
        service.end_view_as(
            other,
            session_id=session.session_id,
            reason="done",
            ticket_ref="SUP-64",
        )
    ended = service.end_view_as(
        actor,
        session_id=session.session_id,
        reason="done",
        ticket_ref="SUP-64",
    )
    assert ended.ended_at is not None
    assert [item.event_type for item in audit.events[-2:]] == [
        "ADMIN_VIEW_AS_STARTED",
        "ADMIN_VIEW_AS_ENDED",
    ]


def test_overview_uses_service_projections_not_fake_percentages():
    service, _, _ = make_service()
    actor = PlatformAdminActor.from_roles("ops-1", frozenset({"OPS"}))
    overview = service.overview(actor)
    assert overview.active_users == 1
    assert overview.active_organizations == 1
    assert overview.daily_generations == 1
    assert overview.failure_rate_basis_points == 5_000
    assert overview.provider_health == "DEGRADED"
    assert "QUEUE_DLQ" in overview.critical_alerts
    assert overview.cost_today_microusd == 143_200
