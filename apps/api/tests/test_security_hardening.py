from fastapi import FastAPI
from fastapi.testclient import TestClient

from lumi_api.security import SecurityConfig, apply_security_hardening, redact_secrets


def _client(*, production: bool = True, max_request_bytes: int = 16) -> TestClient:
    app = FastAPI()
    apply_security_hardening(
        app,
        SecurityConfig(production=production, max_request_bytes=max_request_bytes),
    )

    @app.get("/ok")
    def ok():
        return {"ok": True}

    return TestClient(app)


def test_secret_redaction() -> None:
    value = redact_secrets(
        "Authorization: Bearer abc.def api_key=supersecret password=hunter2"
    )
    assert "abc.def" not in value
    assert "supersecret" not in value
    assert "hunter2" not in value


def test_http_hardening_headers() -> None:
    response = _client().get("/ok")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["strict-transport-security"].startswith("max-age=")


def test_hsts_is_production_only() -> None:
    response = _client(production=False).get("/ok")
    assert response.status_code == 200
    assert "strict-transport-security" not in response.headers


def test_sensitive_query_key_is_rejected() -> None:
    client = _client()
    for key in ("access_token", "api_key", "apikey", "token", "password", "secret"):
        blocked = client.get(f"/ok?{key}=credential")
        assert blocked.status_code == 400


def test_non_sensitive_query_value_is_not_blocked_by_substring() -> None:
    response = _client().get("/ok?note=token%3Dexample")
    assert response.status_code == 200


def test_declared_request_size_limit_is_enforced() -> None:
    response = _client(max_request_bytes=16).get(
        "/ok",
        headers={"content-length": "17"},
    )
    assert response.status_code == 413


def test_invalid_content_length_fails_closed() -> None:
    response = _client().get(
        "/ok",
        headers={"content-length": "not-a-number"},
    )
    assert response.status_code == 400
