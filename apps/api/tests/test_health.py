from fastapi.testclient import TestClient
from lumi_api.main import app


client = TestClient(app)


def test_live_health() -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"service": "api", "status": "ok", "version": "0.0.0-dev"}


def test_ready_health() -> None:
    assert client.get("/health/ready").status_code == 200


def test_version() -> None:
    assert client.get("/version").json()["version"] == "0.0.0-dev"
