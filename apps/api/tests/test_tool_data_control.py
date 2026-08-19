from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any, cast
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from lumi_api.tool_data_control import ToolDataControlRuntime, create_tool_data_control_router

_SECRET = "d" * 64
_PATH = "/internal/v1/tool-data/project/query"
_NOW = 1_700_000_000


class _FakeStore:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def query_project(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(dict(kwargs))
        return {
            "project_id": str(uuid4()),
            "name": "Canonical Project",
            "status": "active",
            "summary": {"goal": "launch"},
        }


def _body() -> bytes:
    return json.dumps(
        {
            "organization_id": str(uuid4()),
            "agent_run_id": str(uuid4()),
            "task_id": str(uuid4()),
            "query": "project.summary",
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


def _client(fake: _FakeStore) -> TestClient:
    app = FastAPI()
    app.include_router(
        create_tool_data_control_router(
            ToolDataControlRuntime(
                store=cast(Any, fake),
                auth_secret=_SECRET,
            )
        )
    )
    return TestClient(app)


def test_signed_project_query_uses_task_derived_scope(monkeypatch) -> None:
    monkeypatch.setattr("lumi_api.tool_data_control.time.time", lambda: float(_NOW))
    fake = _FakeStore()
    body = _body()
    with _client(fake) as client:
        response = client.post(_PATH, content=body, headers=_headers(body))

    assert response.status_code == 200
    assert response.json()["name"] == "Canonical Project"
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["query"] == "project.summary"
    assert "project_id" not in call
    assert set(call) == {"organization_id", "agent_run_id", "task_id", "query"}


def test_unsigned_and_tampered_project_query_are_rejected(monkeypatch) -> None:
    monkeypatch.setattr("lumi_api.tool_data_control.time.time", lambda: float(_NOW))
    fake = _FakeStore()
    body = _body()
    with _client(fake) as client:
        unsigned = client.post(_PATH, content=body, headers={"Content-Type": "application/json"})
        tampered = body.replace(b"project.summary", b"project.changed", 1)
        modified = client.post(_PATH, content=tampered, headers=_headers(body))

    assert unsigned.status_code == 401
    assert modified.status_code == 401
    assert fake.calls == []


def test_agent_runtime_cannot_call_tool_data_control_directly(monkeypatch) -> None:
    monkeypatch.setattr("lumi_api.tool_data_control.time.time", lambda: float(_NOW))
    fake = _FakeStore()
    body = _body()
    with _client(fake) as client:
        response = client.post(
            _PATH,
            content=body,
            headers=_headers(body, service="agent-runtime"),
        )

    assert response.status_code == 401
    assert response.json()["code"] == "TOOL_DATA_CALLER_FORBIDDEN"
    assert fake.calls == []
