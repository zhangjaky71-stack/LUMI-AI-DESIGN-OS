#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER_APP = ROOT / "apps/worker-media/src/lumi_worker_media/app.py"
WORKER_PROJECT = ROOT / "apps/worker-media/pyproject.toml"
HOSTED_RUNTIME = ROOT / "apps/worker-media/src/lumi_worker_media/video_generation_runtime.py"
VIDEO_REPOSITORY = ROOT / "apps/worker-media/src/lumi_worker_media/video_generation_repository.py"
VIDEO_ARTIFACT = ROOT / "apps/worker-media/src/lumi_worker_media/video_generation_artifacts.py"
VIDEO_PORTS = ROOT / "apps/worker-media/src/lumi_worker_media/video_generation_ports.py"
VIDEO_CODEC = ROOT / "apps/worker-media/src/lumi_worker_media/video_generation_codec.py"
VIDEO_PERFORMANCE = ROOT / "services/video-generation/src/lumi_video_generation/performance_ports.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"BLOCK: {message}")


def main() -> None:
    for path in (WORKER_APP, WORKER_PROJECT, VIDEO_PERFORMANCE):
        require(path.is_file(), f"missing {path.relative_to(ROOT)}")

    worker = WORKER_APP.read_text(encoding="utf-8")
    project = WORKER_PROJECT.read_text(encoding="utf-8")
    performance = VIDEO_PERFORMANCE.read_text(encoding="utf-8")

    require("lumi-video-generation" in project, "Worker Media does not depend on video-generation package")
    for path in (HOSTED_RUNTIME, VIDEO_REPOSITORY, VIDEO_ARTIFACT, VIDEO_PORTS, VIDEO_CODEC):
        require(path.is_file(), f"missing {path.relative_to(ROOT)}")

    hosted = HOSTED_RUNTIME.read_text(encoding="utf-8")
    repository = VIDEO_REPOSITORY.read_text(encoding="utf-8")
    artifact = VIDEO_ARTIFACT.read_text(encoding="utf-8")
    ports = VIDEO_PORTS.read_text(encoding="utf-8")
    codec = VIDEO_CODEC.read_text(encoding="utf-8")

    require(
        "HostedVideoGenerationRuntime" in worker and "HostedVideoGenerationRuntime" in hosted,
        "video.render is not bound to Hosted video runtime",
    )
    require(
        "execute_job(" in worker and "_execute_video_generation_job" in worker,
        "video.render does not enter canonical TaskJobStore lifecycle",
    )
    video_block = worker.split('name="lumi.jobs.video.render"', 1)[1].split("@celery_app.task", 1)[0]
    require('"status": "accepted"' not in video_block, "video.render still returns accepted-only placeholder")

    require("PostgresVideoRepository" in hosted, "Hosted video runtime lacks durable PostgreSQL repository")
    require("PostgresVideoArtifactAdapter" in hosted, "Hosted video runtime lacks durable Artifact adapter")
    require("TimedMediaSandbox" in hosted, "Hosted video runtime does not bind real postprocess telemetry")
    require("PerformanceTelemetryContext.from_environ()" in hosted, "Hosted video runtime lacks telemetry provenance")
    require("InMemoryVideoRepository" not in hosted, "Hosted runtime must not use in-memory video repository")
    require("ArtifactHistoryVideoAdapter" not in hosted, "Hosted runtime must not use in-memory ArtifactHistory")

    require("class PostgresVideoRepository" in repository, "durable video repository adapter missing")
    require("video_generation_jobs" in repository, "Postgres video repository is not bound to NODE-48 schema")
    require("video_provider_jobs" in repository, "Postgres video provider-attempt persistence missing")
    require("class PostgresVideoArtifactAdapter" in artifact, "durable video Artifact adapter missing")
    require("artifact_versions" in artifact, "Postgres video Artifact adapter is not bound to canonical Artifact tables")
    require("class HostedVideoOutputAdapter" in ports, "Hosted video output adapter missing")
    require("class HostedVideoMediaSandbox" in ports, "Hosted video media sandbox missing")
    require("encode_video_task_spec" in codec and "decode_video_task_spec" in codec, "durable video spec codec missing")

    require("class TimedMediaSandbox" in performance, "real FFmpeg postprocess timing adapter missing")
    require("PerformanceStage.POSTPROCESS" in performance, "video postprocess stage producer missing")

    print("PASS: Hosted video.render production binding is durable and telemetry-bound")


if __name__ == "__main__":
    main()
