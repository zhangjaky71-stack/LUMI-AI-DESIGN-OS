from lumi_worker_media.topology import (
    DEAD_LETTER_EXCHANGE,
    DOMAIN_EXCHANGE,
    JOBS_EXCHANGE,
    build_dlq_queues,
    build_job_queues,
    domain_queue,
)


def test_job_domain_and_dead_letter_exchanges_are_distinct() -> None:
    assert JOBS_EXCHANGE.name == "lumi.jobs"
    assert JOBS_EXCHANGE.type == "direct"
    assert DOMAIN_EXCHANGE.name == "lumi.domain"
    assert DOMAIN_EXCHANGE.type == "topic"
    assert DEAD_LETTER_EXCHANGE.name == "lumi.dlx"


def test_media_queues_are_separated_and_dead_lettered() -> None:
    queues = {queue.name: queue for queue in build_job_queues()}
    assert set(queues) == {
        "lumi.media.image",
        "lumi.media.video",
        "lumi.media.export",
        "lumi.asset.processing",
    }
    for queue in queues.values():
        assert queue.queue_arguments["x-dead-letter-exchange"] == "lumi.dlx"
    assert len(build_dlq_queues()) == 4


def test_domain_consumer_has_dedicated_queue() -> None:
    queue = domain_queue("asset-indexer", "asset.*")
    assert queue.name == "lumi.domain.asset-indexer"
    assert queue.routing_key == "asset.*"
