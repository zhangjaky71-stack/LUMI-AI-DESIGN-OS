#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIDEO_SERVICE = ROOT / "apps/api/src/lumi_api/generations/video_service.py"
GENERATION_GATEWAY = ROOT / "apps/api/src/lumi_api/generations/gateway.py"
MEDIA_DISPATCH = ROOT / "apps/api/src/lumi_api/media_dispatch.py"
VIDEO_REPOSITORY = ROOT / "apps/worker-media/src/lumi_worker_media/video_generation_repository.py"
API_POSTGRES_TEST = ROOT / "apps/api/tests/integration/test_video_generation_control_plane_postgres.py"
PUBLIC_SYNC_TEST = ROOT / "apps/worker-media/tests/integration/test_video_public_generation_sync_postgres.py"
VIDEO_WORKFLOW = ROOT / ".github/workflows/video-generation.yml"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"BLOCK: {message}")


def read(path: Path) -> str:
    require(path.is_file(), f"missing {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def require_markers(source: str, markers: tuple[str, ...], label: str) -> None:
    missing = [marker for marker in markers if marker not in source]
    require(not missing, f"{label} missing markers: {missing}")


def forbid_markers(source: str, markers: tuple[str, ...], label: str) -> None:
    present = [marker for marker in markers if marker in source]
    require(not present, f"{label} contains forbidden markers: {present}")


def main() -> None:
    service = read(VIDEO_SERVICE)
    gateway = read(GENERATION_GATEWAY)
    dispatch = read(MEDIA_DISPATCH)
    repository = read(VIDEO_REPOSITORY)
    api_test = read(API_POSTGRES_TEST)
    sync_test = read(PUBLIC_SYNC_TEST)
    workflow = read(VIDEO_WORKFLOW)

    require_markers(
        service,
        (
            "class VideoGenerationControlPlane",
            '_OPERATION_TYPE = "api.v1.generation.create"',
            '_VIDEO_CAPABILITY = "video.generate"',
            "canonical_request_hash",
            "pg_advisory_xact_lock",
            "IdempotencyOperation(",
            "Generation(",
            "type=VIDEO_RENDER_JOB_KIND",
            "stage_video_render_dispatch(",
            'status="pending"',
            'operation.status = "succeeded"',
            "operation.response_status = 202",
        ),
        "Hosted video API producer",
    )
    forbid_markers(
        service,
        (
            "import httpx",
            "import requests",
            "Celery(",
            ".delay(",
            "send_task(",
        ),
        "Hosted video API producer DB-only boundary",
    )

    require_markers(
        gateway,
        (
            'if payload.capability == "image.generate"',
            'elif payload.capability == "video.generate"',
            "VideoGenerationControlPlane(session).create(",
            'raise GenerationInvalid("GENERATION_CAPABILITY_UNSUPPORTED")',
        ),
        "generation capability router",
    )

    require_markers(
        dispatch,
        (
            "def build_video_render_dispatch(",
            "def stage_video_render_dispatch(",
            "VIDEO_RENDER_TASK_NAME",
            "VIDEO_RENDER_QUEUE",
            'namespace="video-render"',
        ),
        "canonical video dispatch",
    )

    require_markers(
        repository,
        (
            "async def _sync_public_generation(",
            'row["capability"] != _VIDEO_CAPABILITY',
            "VIDEO_PUBLIC_GENERATION_SCOPE_CONFLICT",
            "VIDEO_PUBLIC_GENERATION_SPEC_CONFLICT",
            "UPDATE generations",
            "_public_generation_result(job)",
            '"provider": shot.provider',
            '"model": shot.model',
        ),
        "Worker public video Generation sync",
    )
    forbid_markers(
        repository,
        (
            '"provider_request_id": shot.provider_request_id',
            '"provider_request_id": job.provider_request_id',
        ),
        "public video Generation result",
    )

    require_markers(
        api_test,
        (
            "test_video_generation_control_plane_transaction_and_replay",
            'capability="video.generate"',
            'assert task.type == "video.render"',
            'assert outbox_rows[0].payload_json["task_name"] == "lumi.jobs.video.render"',
            'assert outbox_rows[0].payload_json["queue"] == "lumi.media.video"',
            'assert idempotency_rows[0].status == "succeeded"',
        ),
        "Video API PostgreSQL producer acceptance",
    )
    require_markers(
        sync_test,
        (
            "test_worker_syncs_public_video_generation_without_provider_request_leak",
            'assert row["status"] == "waiting_external"',
            'assert row["provider"] == "openai"',
            'assert row["model"] == "sora-2"',
            "assert provider_request_id not in json.dumps",
        ),
        "Video public Generation PostgreSQL sync acceptance",
    )

    require_markers(
        workflow,
        (
            "scripts/validate_video_generation_producer_binding.py",
            "apps/api/src/lumi_api/generations/video_service.py",
            "apps/api/src/lumi_api/generations/gateway.py",
            "apps/api/tests/integration/test_video_generation_control_plane_postgres.py",
            "apps/worker-media/tests/integration/test_video_public_generation_sync_postgres.py",
            "Run Video Generation API PostgreSQL producer acceptance",
            "Run Hosted video PostgreSQL acceptance",
        ),
        "Video Generation workflow producer coverage",
    )

    print(
        "PASS: Hosted video generation has a canonical API producer, transactional "
        "dispatch, PostgreSQL acceptance, and provider-neutral public state sync"
    )


if __name__ == "__main__":
    main()
