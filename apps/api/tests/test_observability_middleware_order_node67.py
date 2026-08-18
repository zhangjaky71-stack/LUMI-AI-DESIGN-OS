from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from lumi_api.api.v1.app import create_contract_app
from lumi_api.api.v1.errors import install_error_contract


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


def test_invalid_trace_does_not_short_circuit_authoritative_auth_semantics() -> None:
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
    assert response.status_code == 401
    assert response.json()["code"] != "observability_trace_context_invalid"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "traceparent" in response.headers


def test_downstream_value_error_is_not_misclassified_as_trace_context() -> None:
    app = FastAPI()
    install_error_contract(app)

    @app.get("/boom")
    def boom() -> None:
        raise ValueError("downstream-value-error")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom")

    assert response.status_code == 500
    assert "observability_trace_context_invalid" not in response.text
