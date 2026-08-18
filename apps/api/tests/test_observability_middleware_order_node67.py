from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from lumi_api.api.v1.app import create_contract_app


def test_sensitive_query_is_rejected_before_idempotency_short_circuit() -> None:
    with TestClient(create_contract_app(environment="development")) as client:
        response = client.post(
            "/api/v1/projects?access_token=raw-secret",
            headers={
                "Idempotency-Key": str(uuid4()),
                "X-Organization-ID": str(uuid4()),
            },
            json={},
        )
    assert response.status_code == 400
    assert response.json()["code"] == "security_sensitive_query_forbidden"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "raw-secret" not in response.text


def test_invalid_trace_is_rejected_before_idempotency_short_circuit() -> None:
    with TestClient(create_contract_app(environment="development")) as client:
        response = client.post(
            "/api/v1/projects",
            headers={
                "Idempotency-Key": str(uuid4()),
                "X-Organization-ID": str(uuid4()),
                "traceparent": "invalid-trace-context",
            },
            json={},
        )
    assert response.status_code == 400
    assert response.json()["code"] == "observability_trace_context_invalid"
    assert response.headers["x-content-type-options"] == "nosniff"
