from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from lumi_api.tool_audit_control import (
    CanonicalToolAuditEvent,
    ToolAuditConflictError,
    ToolAuditControlRuntime,
    create_tool_audit_control_router,
)

_SECRET = "a" * 64
_PATH = "/internal/v1/tool-audit/events"
_NOW = 1_700_000_000


class _FakeWriter:
    def __init__(self, *, created: bool = True) -> None:
        self.created = created
        self.events: list[CanonicalToolAuditEvent] = []
        self.conflict = False

    async def write(self, event: CanonicalToolAuditEvent) -> bool:
        self.events.append(event)
        if self.conflict:
            raise ToolAuditConflictError("event id collision")
        return self.created


def _payload(*, actor_id: str = "agent:design") -> dict[str, Any]:
    return {
        "event_id": str(uuid4()),
        "tool_call_id": str(uuid4()),
        "organization_id": str(uuid4()),
        "actor_id": actor_id,
        "actor_agent": "design-agent",
        "resolved_tool": "sandbox.execute@1.0.0",
        "risk": "write_internal",
        "purpose": "render a deterministic design artifact",
        "status": "succeeded",
        "trace_id": "trace-audit-1",
        "arguments": {
            "command": ["python", "render.py"],
            "api_key": "[REDACTED]",
        },
        "replayed": False,
        "side_effect_operation_id": str(uuid4()),
        "approval_id": None,
        "error_code": None,
    }


def _body(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


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


def _client(writer: _FakeWriter) -> TestClient:
    app = FastAPI()
    app.include_router(
        create_tool_audit_control_router(
            ToolAuditControlRuntime(
                writer=writer,
                auth_secret=_SECRET,
            )
        )
    )
    return TestClient(app)


def test_signed_event_maps_to_canonical_append_only_audit(monkeypatch) -> None:
    monkeypatch.setattr("lumi_api.tool_audit_control.time.time", lambda: float(_NOW))
    writer = _FakeWriter()
    payload = _payload()
    body = _body(payload)

    with _client(writer) as client:
        response = client.post(_PATH, content=body, headers=_headers(body))

    assert response.status_code == 201
    assert response.json()["event_id"] == payload["event_id"]
    assert len(writer.events) == 1
    event = writer.events[0]
    assert str(event.id) == payload["event_id"]
    assert event.actor_type == "agent"
    assert event.actor_id is None
    assert event.action == "tool.invoke.succeeded"
    assert event.target_type == "tool_call"
    assert event.request_id == "trace-audit-1"
    assert event.metadata_json["arguments"]["api_key"] == "[REDACTED]"
    assert len(event.metadata_json["event_hash"]) == 64


def test_uuid_actor_is_preserved_as_structured_actor_id(monkeypatch) -> None:
    monkeypatch.setattr("lumi_api.tool_audit_control.time.time", lambda: float(_NOW))
    writer = _FakeWriter()
    actor_id = uuid4()
    payload = _payload(actor_id=str(actor_id))
    body = _body(payload)

    with _client(writer) as client:
        response = client.post(_PATH, content=body, headers=_headers(body))

    assert response.status_code == 201
    assert writer.events[0].actor_id == actor_id
    assert writer.events[0].metadata_json["actor_id_raw"] == str(actor_id)


def test_idempotent_writer_replay_returns_200(monkeypatch) -> None:
    monkeypatch.setattr("lumi_api.tool_audit_control.time.time", lambda: float(_NOW))
    writer = _FakeWriter(created=False)
    payload = _payload()
    body = _body(payload)

    with _client(writer) as client:
        response = client.post(_PATH, content=body, headers=_headers(body))

    assert response.status_code == 200
    assert response.json()["status"] == "replayed"


def test_unredacted_sensitive_argument_is_rejected_before_writer(monkeypatch) -> None:
    monkeypatch.setattr("lumi_api.tool_audit_control.time.time", lambda: float(_NOW))
    writer = _FakeWriter()
    payload = _payload()
    payload["arguments"]["api_key"] = "plaintext-secret"
    body = _body(payload)

    with _client(writer) as client:
        response = client.post(_PATH, content=body, headers=_headers(body))

    assert response.status_code == 422
    assert response.json()["code"] == "TOOL_AUDIT_EVENT_INVALID"
    assert writer.events == []


def test_unsigned_and_wrong_caller_are_rejected_before_writer(monkeypatch) -> None:
    monkeypatch.setattr("lumi_api.tool_audit_control.time.time", lambda: float(_NOW))
    writer = _FakeWriter()
    body = _body(_payload())

    with _client(writer) as client:
        unsigned = client.post(_PATH, content=body, headers={"Content-Type": "application/json"})
        wrong = client.post(
            _PATH,
            content=body,
            headers=_headers(body, service="agent-runtime"),
        )

    assert unsigned.status_code == 401
    assert wrong.status_code == 401
    assert writer.events == []


def test_same_event_id_with_different_content_conflicts(monkeypatch) -> None:
    monkeypatch.setattr("lumi_api.tool_audit_control.time.time", lambda: float(_NOW))
    writer = _FakeWriter()
    writer.conflict = True
    body = _body(_payload())

    with _client(writer) as client:
        response = client.post(_PATH, content=body, headers=_headers(body))

    assert response.status_code == 409
    assert response.json()["code"] == "TOOL_AUDIT_EVENT_CONFLICT"
