from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, cast
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from lumi_api.api.v1.context import RequestContext, get_request_context
from lumi_api.tool_approval_control import (
    ToolApprovalControlRuntime,
    ToolApprovalResolution,
    create_tool_approval_control_router,
    create_tool_approval_public_router,
)

_SECRET = "a" * 64
_PATH = "/internal/v1/tool-approval/resolve"
_NOW = 1_700_000_000


class _FakeStore:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.approval_id = uuid4()

    async def resolve(self, **kwargs: Any) -> ToolApprovalResolution:
        self.calls.append(dict(kwargs))
        return ToolApprovalResolution(
            decision="REQUIRED",
            approval_id=self.approval_id,
            reason_code="TOOL_APPROVAL_REQUIRED",
        )


def _body() -> bytes:
    return json.dumps(
        {
            "organization_id": str(uuid4()),
            "agent_run_id": str(uuid4()),
            "task_id": str(uuid4()),
            "tool_key": "publish.external@1.0.0",
            "purpose": "publish approved artifact",
            "arguments": {"artifact_id": str(uuid4())},
            "approval_id": None,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _headers(body: bytes, *, service: str = "tool-gateway") -> dict[str, str]:
    body_hash = hashlib.sha256(body).hexdigest()
    message = f"{service}\n{_NOW}\nPOST\n{_PATH}\n{body_hash}".encode("utf-8")
    signature = hmac.new(_SECRET.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-Lumi-Service": service,
        "X-Lumi-Timestamp": str(_NOW),
        "X-Lumi-Signature": signature,
    }


def _private_client(fake: _FakeStore) -> TestClient:
    app = FastAPI()
    app.include_router(
        create_tool_approval_control_router(
            ToolApprovalControlRuntime(
                store=cast(Any, fake),
                auth_secret=_SECRET,
            )
        )
    )
    return TestClient(app)


def test_signed_resolve_creates_canonical_scope(monkeypatch) -> None:
    monkeypatch.setattr("lumi_api.tool_approval_control.time.time", lambda: float(_NOW))
    fake = _FakeStore()
    body = _body()
    with _private_client(fake) as client:
        response = client.post(_PATH, content=body, headers=_headers(body))

    assert response.status_code == 200
    assert response.json()["decision"] == "REQUIRED"
    assert response.json()["approval_id"] == str(fake.approval_id)
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["tool_key"] == "publish.external@1.0.0"
    assert len(call["request_hash"]) == 64
    assert call["approval_id"] is None


def test_unsigned_and_tampered_resolve_are_rejected_before_store(monkeypatch) -> None:
    monkeypatch.setattr("lumi_api.tool_approval_control.time.time", lambda: float(_NOW))
    fake = _FakeStore()
    body = _body()
    with _private_client(fake) as client:
        unsigned = client.post(_PATH, content=body, headers={"Content-Type": "application/json"})
        tampered = body.replace(b"publish approved", b"publish altered", 1)
        modified = client.post(_PATH, content=tampered, headers=_headers(body))

    assert unsigned.status_code == 401
    assert modified.status_code == 401
    assert fake.calls == []


def test_wrong_internal_caller_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr("lumi_api.tool_approval_control.time.time", lambda: float(_NOW))
    fake = _FakeStore()
    body = _body()
    with _private_client(fake) as client:
        response = client.post(
            _PATH,
            content=body,
            headers=_headers(body, service="agent-runtime"),
        )
    assert response.status_code == 401
    assert response.json()["code"] == "TOOL_APPROVAL_CALLER_FORBIDDEN"
    assert fake.calls == []


def test_editor_cannot_decide_high_risk_tool_approval() -> None:
    app = FastAPI()
    factory = cast(async_sessionmaker[AsyncSession], None)
    app.include_router(create_tool_approval_public_router(factory))
    organization_id = uuid4()
    actor_id = uuid4()

    async def context_override() -> RequestContext:
        return RequestContext(
            organization_id=organization_id,
            request_id="approval-permission-test",
            actor_id=actor_id,
            actor_type="user",
            permissions=frozenset({"project.read", "project.write"}),
        )

    app.dependency_overrides[get_request_context] = context_override
    with TestClient(app) as client:
        response = client.post(
            f"/projects/{uuid4()}/tool-approvals/{uuid4()}:decide",
            json={"decision": "APPROVE"},
            headers={"Idempotency-Key": "approval-decision-0001"},
        )

    assert response.status_code == 403
    assert response.json()["code"] == "TOOL_APPROVAL_PERMISSION_DENIED"
