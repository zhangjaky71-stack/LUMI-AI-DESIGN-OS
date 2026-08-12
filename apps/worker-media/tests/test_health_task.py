from lumi_worker_media.app import celery_app, health_ping


def test_health_task_without_broker() -> None:
    assert celery_app.main == "lumi-worker-media"
    assert health_ping.run()["status"] == "ok"
