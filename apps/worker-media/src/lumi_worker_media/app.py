import os

from celery import Celery

broker = os.getenv("RABBITMQ_URL", "memory://")
backend = "cache+memory://" if broker == "memory://" else None
celery_app = Celery("lumi-worker-media", broker=broker, backend=backend)


@celery_app.task(name="health.ping")
def health_ping() -> dict[str, str]:
    return {"service": "worker-media", "status": "ok", "version": "0.0.0-dev"}
