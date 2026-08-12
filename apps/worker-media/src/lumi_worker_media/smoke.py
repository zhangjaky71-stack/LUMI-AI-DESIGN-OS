import json

from lumi_worker_media.app import celery_app, health_ping


def main() -> None:
    assert celery_app.main == "lumi-worker-media"
    print(json.dumps(health_ping.run()))
