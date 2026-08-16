from __future__ import annotations

from uuid import UUID

from lumi_worker_media.app import celery_app

ORG = UUID("01910000-0000-7000-8000-000000000001")
PROJECT = UUID("01910000-0000-7000-8000-000000000031")
JOB = UUID("01910000-0000-7000-8000-000000000821")


def main() -> None:
    health = celery_app.send_task(
        "health.ping",
        queue="lumi.media.image",
        routing_key="image.transform",
    )
    assert health.get(timeout=30) == {
        "service": "worker-media",
        "status": "ok",
        "version": "0.0.0-dev",
    }
    result = celery_app.send_task(
        "lumi.jobs.image.transform",
        args=[
            {
                "job_id": str(JOB),
                "organization_id": str(ORG),
                "project_id": str(PROJECT),
            }
        ],
        queue="lumi.media.image",
        routing_key="image.transform",
    )
    payload = result.get(timeout=30)
    assert payload["job_id"] == str(JOB)
    assert payload["kind"] == "image.transform"
    assert payload["status"] == "processed"
    print("NODE19_CELERY_WORKER_PASS")


if __name__ == "__main__":
    main()
