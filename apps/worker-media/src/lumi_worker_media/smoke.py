import json

from lumi_worker_media.app import celery_app, health_payload


def main() -> None:
    assert celery_app.main == "lumi-worker-media"
    assert "health.ping" in celery_app.tasks
    print(json.dumps(health_payload()))
