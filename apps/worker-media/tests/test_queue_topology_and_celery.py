from __future__ import annotations

from kombu import Connection

from lumi_worker_media.app import celery_app
from lumi_worker_media.topology import (
    DEAD_LETTER_EXCHANGE,
    DOMAIN_EXCHANGE,
    JOBS_EXCHANGE,
    build_job_dlq_queues,
    build_job_queues,
    declare_topology,
    domain_dlq,
    domain_queue,
)


def test_celery_reliability_flags_do_not_pretend_exactly_once() -> None:
    assert celery_app.conf.task_acks_late is False
    assert celery_app.conf.task_reject_on_worker_lost is False
    assert celery_app.conf.worker_prefetch_multiplier == 1
    assert celery_app.conf.task_serializer == "json"
    assert set(celery_app.conf.accept_content) == {"json"}


def test_job_routes_are_physically_separated() -> None:
    routes = celery_app.conf.task_routes
    assert routes["lumi.jobs.image.transform"]["queue"] == "lumi.media.image"
    assert routes["lumi.jobs.video.render"]["queue"] == "lumi.media.video"
    assert routes["lumi.jobs.export.package"]["queue"] == "lumi.media.export"
    assert routes["lumi.jobs.asset.validate"]["queue"] == "lumi.asset.processing"


def test_topology_is_idempotently_declarable_on_memory_transport() -> None:
    assert JOBS_EXCHANGE.name == "lumi.jobs" and JOBS_EXCHANGE.type == "direct"
    assert DOMAIN_EXCHANGE.name == "lumi.domain" and DOMAIN_EXCHANGE.type == "topic"
    assert DEAD_LETTER_EXCHANGE.name == "lumi.dlx" and DEAD_LETTER_EXCHANGE.type == "topic"
    assert {queue.name for queue in build_job_queues()} == {
        "lumi.media.image",
        "lumi.media.video",
        "lumi.media.export",
        "lumi.asset.processing",
    }
    assert {queue.name for queue in build_job_dlq_queues()} == {
        "lumi.media.image.dlq",
        "lumi.media.video.dlq",
        "lumi.media.export.dlq",
        "lumi.asset.processing.dlq",
    }
    queue = domain_queue("asset-indexer.v1", "lumi.asset.#")
    assert queue.name == "lumi.domain.asset-indexer.v1"
    assert queue.queue_arguments is not None
    assert queue.queue_arguments["x-queue-type"] == "quorum"
    assert domain_dlq("asset-indexer.v1").name == "lumi.domain.asset-indexer.v1.dlq"
    with Connection("memory://") as connection:
        declare_topology(
            connection,
            domain_consumers=(("asset-indexer.v1", "lumi.asset.#"),),
        )
        declare_topology(
            connection,
            domain_consumers=(("asset-indexer.v1", "lumi.asset.#"),),
        )
