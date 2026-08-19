from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from lumi_api.idempotency.contracts import ClaimDecision, OperationStatus
from lumi_api.idempotency.gateway import OperationClaim, OperationSnapshot
from lumi_api.tool_side_effect_control import (
    ToolSideEffectControlRuntime,
    create_tool_side_effect_control_router,
)

_SECRET = "s" * 64
_PATH = "/internal/v1/side-effects/claim"
_NOW = 1_700_000_000


class _FakeSideEffectGateway:
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


def _body(*, organization_id: UUID | None = None) -> bytes:
    payload = {
        "organization_id": str(organization_id or uuid4()),
        "operation_type": "tool:sandbox.execute:1.0.0",
        "idempotency_key": "idem-tool-1",
        "request": {
            "tool": "sandbox.execute@1.0.0",
            "arguments": {"command": ["python", "-V"]},
        },
        "business_scope_id": str(uuid4()),
        "lease_owner": "tool-gateway:test:lease-1",
        "lease_seconds": 120,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _signed_headers(body: bytes, *, service: str = "tool-gateway", timestamp: int = _NOW) -> dict[str, str]:
    body_hash = hashlib.sha256(body).hexdigest()
    message = f"{service}\n{timestamp}\nPOST\n{_PATH}\n{body_hash}".encode("utf-8")
    signature = hmac.new(_SECRET.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-Lumi-Service": service,
        "X-Lumi-Timestamp": str(timestamp),
        "X-Lumi-Signature": signature,
    }


def _client(fake: _FakeSideEffectGateway) -> TestClient:
    app = FastAPI()
    app.include_router(
        create_tool_side_effect_control_router(
            ToolSideEffectControlRuntime(
                gateway=fake,  # type: ignore[arg-type]
                auth_secret=_SECRET,
            )
        )
    )
    return TestClient(app)


def test_signed_claim_preserves_canonical_node20_context(monkeypatch) -> None:
    monkeypatch.setattr("lumi_api.tool_side_effect_control.time.time", lambda: float(_NOW))
    fake = _FakeSideEffectGateway()
    organization_id = uuid4()
    body = _body(organization_id=organization_id)

    with _client(fake) as client:
        response = client.post(_PATH, content=body, headers=_signed_headers(body))

    assert response.status_code == 200
    assert response.json()["decision"] == "execute"
    assert len(fake.claim_calls) == 1
    context, lease_owner = fake.claim_calls[0]
    assert context.organization_id == organization_id
    assert context.operation_type == "tool:sandbox.execute:1.0.0"
    assert context.idempotency_key == "idem-tool-1"
    assert context.lease_seconds == 120
    assert context.request["tool"] == "sandbox.execute@1.0.0"
    assert lease_owner == "tool-gateway:test:lease-1"


def test_unsigned_claim_is_rejected_before_ledger(monkeypatch) -> None:
    monkeypatch.setattr("lumi_api.tool_side_effect_control.time.time", lambda: float(_NOW))
    fake = _FakeSideEffectGateway()
    body = _body()

    with _client(fake) as client:
        response = client.post(_PATH, content=body, headers={"Content-Type": "application/json"})

    assert response.status_code == 401
    assert response.json()["code"] == "SIDE_EFFECT_CONTROL_CALLER_FORBIDDEN"
    assert fake.claim_calls == []


def test_tampered_body_is_rejected_before_ledger(monkeypatch) -> None:
    monkeypatch.setattr("lumi_api.tool_side_effect_control.time.time", lambda: float(_NOW))
    fake = _FakeSideEffectGateway()
    signed_body = _body()
    tampered = signed_body.replace(b"python", b"python3", 1)

    with _client(fake) as client:
        response = client.post(_PATH, content=tampered, headers=_signed_headers(signed_body))

    assert response.status_code == 401
    assert response.json()["code"] == "SIDE_EFFECT_CONTROL_SIGNATURE_INVALID"
    assert fake.claim_calls == []


def test_wrong_service_is_rejected_even_with_valid_hmac(monkeypatch) -> None:
    monkeypatch.setattr("lumi_api.tool_side_effect_control.time.time", lambda: float(_NOW))
    fake = _FakeSideEffectGateway()
    body = _body()

    with _client(fake) as client:
        response = client.post(
            _PATH,
            content=body,
            headers=_signed_headers(body, service="agent-runtime"),
        )

    assert response.status_code == 401
    assert response.json()["code"] == "SIDE_EFFECT_CONTROL_CALLER_FORBIDDEN"
    assert fake.claim_calls == []


def test_expired_signature_is_rejected_before_ledger(monkeypatch) -> None:
    monkeypatch.setattr(
        "lumi_api.tool_side_effect_control.time.time",
        lambda: float(_NOW + 1_000),
    )
    fake = _FakeSideEffectGateway()
    body = _body()

    with _client(fake) as client:
        response = client.post(_PATH, content=body, headers=_signed_headers(body))

    assert response.status_code == 401
    assert response.json()["code"] == "SIDE_EFFECT_CONTROL_TIMESTAMP_EXPIRED"
    assert fake.claim_calls == []
