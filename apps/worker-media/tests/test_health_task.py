from lumi_worker_media.app import celery_app, health_payload


def test_health_task_is_registered() -> None:
    assert celery_app.main == "lumi-worker-media"
    assert "health.ping" in celery_app.tasks


def test_health_payload_without_broker() -> None:
    assert health_payload() == {
        "service": "worker-media",
        "status": "ok",
        "version": "0.0.0-dev",
    }
