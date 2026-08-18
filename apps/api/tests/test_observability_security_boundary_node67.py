from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from lumi_api.api.v1.app import create_contract_app
from lumi_api.api.v1.errors import install_error_contract


def test_invalid_trace_response_keeps_node66_security_headers() -> None:
    with TestClient(create_contract_app(environment="development")) as client:
        response = client.get(
            "/api/openapi.json",
            headers={"traceparent": "not-a-valid-traceparent"},
        )
    assert response.status_code == 400
    assert response.json()["code"] == "observability_trace_context_invalid"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_production_invalid_trace_response_keeps_hsts() -> None:
    with TestClient(create_contract_app(environment="production")) as client:
        response = client.get(
            "/api/v1/health/live",
            headers={"traceparent": "not-a-valid-traceparent"},
        )
    assert response.status_code == 400
    assert response.headers["strict-transport-security"].startswith("max-age=63072000")
    assert response.headers["x-content-type-options"] == "nosniff"


def test_business_value_error_is_not_reclassified_as_trace_context_error() -> None:
    app = FastAPI()
    install_error_contract(app)

    @app.get("/business-value-error")
    def business_value_error():
        raise ValueError("BUSINESS_DOMAIN_VALUE_ERROR")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/business-value-error")
    assert response.status_code == 500
    assert "observability_trace_context_invalid" not in response.text
