from lumi_worker_media.app import celery_app


def test_node19_does_not_enable_late_ack_before_node20() -> None:
    assert celery_app.conf.task_acks_late is False
    assert celery_app.conf.task_reject_on_worker_lost is False
    assert celery_app.conf.worker_prefetch_multiplier == 1


def test_media_task_routes_are_queue_separated() -> None:
    routes = celery_app.conf.task_routes
    assert routes["lumi.jobs.image.transform"]["queue"] == "lumi.media.image"
    assert routes["lumi.jobs.video.render"]["queue"] == "lumi.media.video"
    assert routes["lumi.jobs.export.package"]["queue"] == "lumi.media.export"
    assert routes["lumi.assets.validate"]["queue"] == "lumi.asset.processing"
