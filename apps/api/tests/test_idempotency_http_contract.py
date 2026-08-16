from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import FastAPI, Header
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict

from lumi_api.api.v1.errors import install_error_contract
from lumi_api.api.v1.idempotency_middleware import IdempotencyReplayMiddleware
from lumi_api.idempotency import (
    CompensationMode,
    MemoryIdempotencyStore,
    OperationRequest,
    SideEffectGateway,
    SideEffectKind,
    SideEffectOutcome,
    canonical_request_hash,
)

ORG = UUID("01910000-0000-7000-8000-000000000001")
NOW = datetime(2026, 8, 16, 9, 40, tzinfo=UTC)


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str


def test_http_replay_header_and_different_body_conflict() -> None:
    app = FastAPI()
    install_error_contract(app)
    app.add_middleware(IdempotencyReplayMiddleware)
    store = MemoryIdempotencyStore()
    gateway = SideEffectGateway(store)
    calls = 0

    @app.post("/write")
    async def write(
        body: Body,
        idempotency_key: str = Header(alias="Idempotency-Key"),
    ) -> dict[str, str]:
        request = OperationRequest(
            organization_id=ORG,
            operation_type="api.test.write",
            idempotency_key=idempotency_key,
            request_hash=canonical_request_hash(body),
            side_effect_kind=SideEffectKind.GENERIC_WRITE,
            compensation_mode=CompensationMode.COMPENSATABLE,
        )

        async def effect(_context):
            nonlocal calls
            calls += 1
            return SideEffectOutcome(result={"value": body.value})

        outcome = await gateway.execute(
            request,
            effect,
            lease_owner=f"http-{calls}",
            now=NOW,
        )
        return {"value": str(outcome.result["value"])}

    client = TestClient(app)
    first = client.post(
        "/write",
        headers={"Idempotency-Key": "node20-http-key"},
        json={"value": "one"},
    )
    assert first.status_code == 200
    assert "Idempotent-Replayed" not in first.headers

    replay = client.post(
        "/write",
        headers={"Idempotency-Key": "node20-http-key"},
        json={"value": "one"},
    )
    assert replay.status_code == 200
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert replay.json() == first.json()
    assert calls == 1

    conflict = client.post(
        "/write",
        headers={"Idempotency-Key": "node20-http-key"},
        json={"value": "different"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_REQUEST"
    assert calls == 1
