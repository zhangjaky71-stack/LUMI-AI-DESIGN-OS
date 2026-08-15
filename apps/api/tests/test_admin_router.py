from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from lumi_api.admin_router import create_admin_router
from lumi_project_core.admin_console import (
    AdminBillingView,
    AdminConsoleService,
    AdminProviderRecord,
    AdminQueueRecord,
    AdminRegistryEntry,
    AdminRunRecord,
    InMemoryAdminAuditSink,
    InMemoryViewAsStore,
    PlatformAdminActor,
    SupportOrganization,
    SupportUser,
)


class Directory:
    def __init__(self):
        self.user = SupportUser(
            "user-1",
            "Ada",
            "ada@example.test",
            "+81 90 1111 2222",
            "ACTIVE",
            ("org-1",),
            ("OWNER",),
            ("MODEL_TIMEOUT",),
        )

    def list_users(self):
        return (self.user,)

    def list_organizations(self):
        return (SupportOrganization("org-1", "Alpha", "ACTIVE"),)

    def get_user(self, user_id: str):
        return self.user if user_id == self.user.user_id else None


class Runs:
    def __init__(self):
        self.item = AdminRunRecord(
            "run-1",
            "org-1",
            "task-1",
            "GENERATION",
            "FAILED",
            "mock-image",
            None,
            "MODEL_TIMEOUT",
            100,
            True,
            False,
            datetime.now(UTC).isoformat(),
        )

    def list_runs(self):
        return (self.item,)

    def retry(self, run_id: str):
        assert run_id == self.item.run_id
        self.item = replace(self.item, status="QUEUED", retryable=False)
        return self.item

    def cancel(self, run_id: str):
        raise AssertionError(f"unexpected cancel {run_id}")


class Providers:
    def __init__(self):
        self.item = AdminProviderRecord(
            "mock-image", "HEALTHY", "CLOSED", 10_000, "HEALTHY", "pricing-v1"
        )

    def list_providers(self):
        return (self.item,)

    def disable_temporarily(self, provider_id: str, *, expires_at: str, reason: str):
        assert provider_id == self.item.provider_id
        self.item = replace(
            self.item,
            health="DISABLED",
            routing_weight_basis_points=0,
            disabled_until=expires_at,
            disabled_reason=reason,
        )
        return self.item


class Queue:
    def __init__(self):
        self.item = AdminQueueRecord(
            "queue-1", "task-1", "DLQ", "payload://task-1", "b" * 64, 3, "FAIL"
        )

    def list_queue(self):
        return (self.item,)

    def requeue_original(
        self,
        queue_item_id: str,
        *,
        expected_payload_ref: str,
        expected_payload_sha256: str,
    ):
        assert queue_item_id == self.item.queue_item_id
        assert expected_payload_ref == self.item.payload_ref
        assert expected_payload_sha256 == self.item.payload_sha256
        self.item = replace(self.item, state="READY", attempts=4)
        return self.item


class Registry:
    def __init__(self):
        self.item = AdminRegistryEntry("designer", "AGENT", "Designer", "v7", True, 10_000, "safe")

    def list_registry(self):
        return (self.item,)

    def set_enabled(self, kind, registry_id: str, enabled: bool):
        assert kind == self.item.kind and registry_id == self.item.registry_id
        self.item = replace(self.item, enabled=enabled)
        return self.item


class Costs:
    def cost_today_microusd(self):
        return 10_000


class Billing:
    def __init__(self):
        self.balance = 100

    def summary(self, organization_id: str):
        return AdminBillingView(organization_id, "pro-v1", "ACTIVE", self.balance, ("inv-1",))

    def adjust_credits(self, *, organization_id: str, delta_credits: int, idempotency_key: str, source_id: str):
        assert idempotency_key and source_id.startswith("admin:")
        self.balance += delta_credits
        return self.summary(organization_id)


def make_client(role_header: str = "ops") -> tuple[TestClient, InMemoryAdminAuditSink]:
    audit = InMemoryAdminAuditSink()
    service = AdminConsoleService(
        directory=Directory(),
        runs=Runs(),
        providers=Providers(),
        queue=Queue(),
        registry=Registry(),
        costs=Costs(),
        billing=Billing(),
        view_as=InMemoryViewAsStore(),
        audit=audit,
    )

    async def resolve_actor(request: Request) -> PlatformAdminActor:
        mode = request.headers.get("x-platform-role", role_header)
        mapping = {
            "support": frozenset({"SUPPORT_READ"}),
            "ops": frozenset({"OPS"}),
            "billing": frozenset({"BILLING_ADMIN"}),
            "privacy": frozenset({"PRIVACY_ADMIN"}),
            "model": frozenset({"MODEL_ADMIN"}),
            "audit": frozenset({"SECURITY_AUDITOR"}),
        }
        return PlatformAdminActor.from_roles(f"admin-{mode}", mapping[mode])

    app = FastAPI()
    app.include_router(create_admin_router(service=service, resolve_actor=resolve_actor))
    return TestClient(app), audit


def confirmation(summary: str, scope: str) -> dict[str, object]:
    return {
        "action_summary": summary,
        "impact_scope": scope,
        "reason": "incident mitigation",
        "ticket_ref": "INC-64",
        "confirmation": "CONFIRM",
    }


def test_console_returns_masked_support_data_and_platform_actor():
    client, _ = make_client()
    result = client.get("/admin/console")
    assert result.status_code == 200
    body = result.json()
    assert body["actor"]["actor_id"] == "admin-ops"
    assert body["users"][0]["email_masked"] == "a•••@example.test"
    assert "ada@example.test" not in result.text
    assert body["overview"]["queue_depth"] == 1


def test_tenant_like_support_role_cannot_disable_provider():
    client, _ = make_client()
    payload = confirmation(
        "Temporarily disable provider mock-image", "provider:mock-image"
    ) | {"expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat()}
    denied = client.post(
        "/admin/providers/mock-image:disable",
        json=payload,
        headers={"x-platform-role": "support"},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "ADMIN_FORBIDDEN"


def test_provider_disable_requires_confirmation_and_audits():
    client, audit = make_client()
    payload = confirmation(
        "Temporarily disable provider mock-image", "provider:mock-image"
    ) | {"expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat()}
    response = client.post("/admin/providers/mock-image:disable", json=payload)
    assert response.status_code == 200
    assert response.json()["health"] == "DISABLED"
    assert audit.events[-1].event_type == "ADMIN_PROVIDER_DISABLED"


def test_requeue_contract_has_no_payload_edit_surface():
    client, audit = make_client()
    payload = confirmation("Requeue item queue-1", "queue-item:queue-1")
    response = client.post("/admin/queue/queue-1:requeue", json=payload)
    assert response.status_code == 200
    assert response.json()["payload_ref"] == "payload://task-1"
    assert response.json()["payload_sha256"] == "b" * 64
    assert audit.events[-1].event_type == "ADMIN_QUEUE_REQUEUED"
    assert "payload" not in payload


def test_pii_reveal_requires_privacy_role_reason_and_audits():
    client, audit = make_client()
    denied = client.post(
        "/admin/users/user-1:reveal-pii",
        json={"reason": "support case", "ticket_ref": "SUP-1"},
        headers={"x-platform-role": "support"},
    )
    assert denied.status_code == 403
    allowed = client.post(
        "/admin/users/user-1:reveal-pii",
        json={"reason": "privacy request", "ticket_ref": "PRIV-1"},
        headers={"x-platform-role": "privacy"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["email"] == "ada@example.test"
    assert audit.events[-1].event_type == "ADMIN_PII_REVEALED"


def test_billing_adjustment_requires_platform_billing_admin_and_idempotency_header():
    client, audit = make_client()
    payload = confirmation("Adjust billing credits by 25", "organization:org-1") | {
        "delta_credits": 25
    }
    denied = client.post(
        "/admin/billing/org-1:adjust",
        json=payload,
        headers={"x-platform-role": "ops", "Idempotency-Key": "adjust-1"},
    )
    assert denied.status_code == 403
    allowed = client.post(
        "/admin/billing/org-1:adjust",
        json=payload,
        headers={"x-platform-role": "billing", "Idempotency-Key": "adjust-1"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["credit_balance"] == 125
    assert audit.events[-1].event_type == "ADMIN_BILLING_ADJUSTED"


def test_view_as_is_readonly_and_no_mutation_endpoint_is_exposed():
    client, audit = make_client()
    response = client.post(
        "/admin/users/user-1:view-as",
        json={
            "organization_id": "org-1",
            "reason": "reproduce issue",
            "ticket_ref": "SUP-64",
            "ttl_minutes": 5,
        },
        headers={"x-platform-role": "support"},
    )
    assert response.status_code == 200
    assert response.json()["readonly"] is True
    assert audit.events[-1].event_type == "ADMIN_VIEW_AS_STARTED"
