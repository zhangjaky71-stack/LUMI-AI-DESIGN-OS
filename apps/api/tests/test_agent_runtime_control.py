from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from lumi_api.agent_runtime_control import (
    AgentRuntimeControlRuntime,
    create_agent_runtime_control_router,
)
from lumi_api.idempotency.contracts import ClaimDecision, OperationStatus
from lumi_api.idempotency.gateway import OperationClaim, OperationSnapshot

_SECRET = "a" * 64
_PATH = "/internal/v1/agent-control/operations/claim"
_NOW = 1_700_000_000


class _FakeGateway:
    def __init__(self) -> None:
        self.claim_calls: list[tuple[Any, str]] = []

    async def claim(self, context: Any, *, lease_owner: str) -> OperationClaim:
        self.claim_calls.append((context, lease_owner))
        now = datetime.now(UTC)
        return OperationClaim(
            ClaimDecision.EXECUTE,
            OperationSnapshot(
                id=uuid4(),
                organization_id=context.organization_id,
                operation_type=context.operation_type,
                idempotency_key=context.idempotency_key,
                request_hash=context.request_hash,
                status=OperationStatus.IN_PROGRESS,
                lease_owner=lease_owner,
                lease_expires_at=now + timedelta(seconds=context.lease_seconds),
                provider_attempt_started_at=None,
                provider_request_id=None,
                result_ref=None,
                result_json={},
                response_status=None,
                error_code=None,
                error_category=None,
                completed_at=None,
                attempt_count=1,
                ambiguity_reason=None,
            ),
        )


def _body(
    *,
    organization_id: UUID | None = None,
    operation_id: UUID | None = None,
) -> bytes:
    payload = {
        "organization_id": str(organization_id or uuid4()),
        "operation_id": str(operation_id or uuid4()),
        "operation_type": "langgraph.start",
        "request_hash": "b" * 64,
        "lease_owner": "agent-runtime:test:lease-1",
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _signed_headers(
    body: bytes,
    *,
    service: str = "agent-runtime",
    timestamp: int = _NOW,
) -> dict[str, str]:
    body_hash = hashlib.sha256(body).hexdigest()
    message = f"{service}\n{timestamp}\nPOST\n{_PATH}\n{body_hash}".encode("utf-8")
    signature = hmac.new(_SECRET.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-Lumi-Service": service,
        "X-Lumi-Timestamp": str(timestamp),
        "X-Lumi-Signature": signature,
    }


def _client(fake: _FakeGateway) -> TestClient:
    app = FastAPI()
    app.include_router(
        create_agent_runtime_control_router(
            AgentRuntimeControlRuntime(
                gateway=fake,  # type: ignore[arg-type]
                session_factory=None,  # type: ignore[arg-type]
                auth_secret=_SECRET,
            )
        )
    )
    return TestClient(app)


def test_signed_claim_binds_to_canonical_node20_identity(monkeypatch) -> None:
    monkeypatch.setattr("lumi_api.agent_runtime_control.time.time", lambda: float(_NOW))
    fake = _FakeGateway()
    organization_id = uuid4()
    operation_id = uuid4()
    body = _body(organization_id=organization_id, operation_id=operation_id)

    with _client(fake) as client:
        response = client.post(_PATH, content=body, headers=_signed_headers(body))

    assert response.status_code == 200
    assert response.json()["decision"] == "execute"
    assert len(fake.claim_calls) == 1
    context, lease_owner = fake.claim_calls[0]
    assert context.organization_id == organization_id
    assert context.operation_type == "langgraph.start"
    assert context.idempotency_key == str(operation_id)
    assert context.business_scope_id == operation_id
    assert context.request == {"control_plane_request_hash": "b" * 64}
    assert lease_owner == "agent-runtime:test:lease-1"


def test_unsigned_claim_is_rejected_before_ledger(monkeypatch) -> None:
    monkeypatch.setattr("lumi_api.agent_runtime_control.time.time", lambda: float(_NOW))
    fake = _FakeGateway()
    body = _body()

    with _client(fake) as client:
        response = client.post(
            _PATH,
            content=body,
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code == 401
    assert response.json()["code"] == "AGENT_CONTROL_CALLER_FORBIDDEN"
    assert fake.claim_calls == []


def test_wrong_service_is_rejected_before_ledger(monkeypatch) -> None:
    monkeypatch.setattr("lumi_api.agent_runtime_control.time.time", lambda: float(_NOW))
    fake = _FakeGateway()
    body = _body()

    with _client(fake) as client:
        response = client.post(
            _PATH,
            content=body,
            headers=_signed_headers(body, service="tool-gateway"),
        )

    assert response.status_code == 401
    assert response.json()["code"] == "AGENT_CONTROL_CALLER_FORBIDDEN"
    assert fake.claim_calls == []


def test_tampered_claim_is_rejected_before_ledger(monkeypatch) -> None:
    monkeypatch.setattr("lumi_api.agent_runtime_control.time.time", lambda: float(_NOW))
    fake = _FakeGateway()
    signed_body = _body()
    tampered = signed_body.replace(b"langgraph.start", b"langgraph.resume", 1)

    with _client(fake) as client:
        response = client.post(
            _PATH,
            content=tampered,
            headers=_signed_headers(signed_body),
        )

    assert response.status_code == 401
    assert response.json()["code"] == "AGENT_CONTROL_SIGNATURE_INVALID"
    assert fake.claim_calls == []


def test_expired_signature_is_rejected_before_ledger(monkeypatch) -> None:
    monkeypatch.setattr(
        "lumi_api.agent_runtime_control.time.time",
        lambda: float(_NOW + 1_000),
    )
    fake = _FakeGateway()
    body = _body()

    with _client(fake) as client:
        response = client.post(_PATH, content=body, headers=_signed_headers(body))

    assert response.status_code == 401
    assert response.json()["code"] == "AGENT_CONTROL_TIMESTAMP_EXPIRED"
    assert fake.claim_calls == []
