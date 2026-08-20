#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIDEO_SERVICE = ROOT / "apps/api/src/lumi_api/generations/video_service.py"
GENERATION_GATEWAY = ROOT / "apps/api/src/lumi_api/generations/gateway.py"
MEDIA_DISPATCH = ROOT / "apps/api/src/lumi_api/media_dispatch.py"
VIDEO_REPOSITORY = ROOT / "apps/worker-media/src/lumi_worker_media/video_generation_repository.py"
OUTBOX_CLI = ROOT / "apps/worker-media/src/lumi_worker_media/cli.py"
JOB_DISPATCH_RUNTIME = ROOT / "apps/worker-media/src/lumi_worker_media/job_dispatch_runtime.py"
COMPUTE_IAC = ROOT / "infra/iac/modules/compute/main.tf"
RUNTIME_MANIFEST = ROOT / "production/runtime-images/manifest-v1.json"
API_POSTGRES_TEST = ROOT / "apps/api/tests/integration/test_video_generation_control_plane_postgres.py"
OUTBOX_POSTGRES_TEST = ROOT / "apps/api/tests/integration/test_video_outbox_dispatch_postgres.py"
PUBLIC_SYNC_TEST = ROOT / "apps/worker-media/tests/integration/test_video_public_generation_sync_postgres.py"
VIDEO_WORKFLOW = ROOT / ".github/workflows/video-generation.yml"
ENVIRONMENT_IAC = {
    environment: ROOT / f"infra/iac/environments/{environment}/app/main.tf"
    for environment in ("staging", "production")
}
REQUIRED_RUNTIME_IMAGES = {
    "api",
    "agent-runtime",
    "model-gateway",
    "tool-gateway",
    "worker-media",
    "sandbox-runtime",
}


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


def service_block(text: str, service: str) -> str:
    marker = f"    {service} = {{"
    start = text.find(marker)
    require(start >= 0, f"missing Terraform service block: {service}")
    brace = text.find("{", start)
    depth = 0
    for index in range(brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise SystemExit(f"BLOCK: unterminated Terraform service block: {service}")


def validate_outbox_deployment() -> None:
    compute = read(COMPUTE_IAC)
    require_markers(
        compute,
        (
            'contains(["sandbox-runtime", "outbox-dispatcher"], name)',
            "? [var.app_security_group_id, var.sandbox_egress_security_group_id]",
            ": [var.app_security_group_id, var.app_internet_egress_security_group_id]",
        ),
        "outbox dispatcher restricted egress",
    )

    for environment, path in ENVIRONMENT_IAC.items():
        block = service_block(read(path), "outbox-dispatcher")
        require_markers(
            block,
            (
                "image         = var.worker_media_image",
                '"python"',
                '"-m"',
                '"lumi_worker_media.cli"',
                '"dispatch-outbox"',
                '"--watch"',
                '"--interval"',
                'LUMI_ROLE = "outbox-dispatcher"',
                'LUMI_DATABASE_URL = local.secret_arns["database/app"]',
                'LUMI_RABBITMQ_URL = local.secret_arns["rabbitmq/url"]',
                "s3_bucket_arns         = []",
            ),
            f"{environment} outbox dispatcher",
        )
        forbid_markers(
            block,
            (
                "LUMI_MODEL_PROVIDER_SECRET",
                "LUMI_MEDIA_PROVIDER_SECRET",
                "LUMI_MODEL_GATEWAY_AUTH_SECRET",
                "LUMI_SANDBOX_RUNTIME_AUTH_SECRET",
                "LUMI_AUTH_SIGNING_SECRET",
                "LUMI_BRAVE_SEARCH_API_KEY",
                'local.secret_arns["providers/',
                'local.bucket_arns[',
            ),
            f"{environment} outbox dispatcher least privilege",
        )
        desired_marker = "desired_count = 1" if environment == "staging" else "desired_count = 2"
        min_marker = "min_capacity  = 1" if environment == "staging" else "min_capacity  = 2"
        require_markers(
            block,
            (desired_marker, min_marker),
            f"{environment} outbox dispatcher always-on capacity",
        )


def validate_runtime_provenance() -> None:
    payload = json.loads(read(RUNTIME_MANIFEST))
    require(isinstance(payload, dict), "runtime image manifest must be an object")
    runtimes = payload.get("runtimes")
    require(isinstance(runtimes, dict), "runtime image manifest runtimes missing")
    require(
        set(runtimes) == REQUIRED_RUNTIME_IMAGES,
        "outbox dispatcher must reuse worker-media image; runtime image set must remain exactly six",
    )

    api = runtimes.get("api")
    worker = runtimes.get("worker-media")
    require(isinstance(api, dict) and isinstance(worker, dict), "api/worker runtime provenance missing")
    api_sources = set(api.get("source_paths") or [])
    worker_sources = set(worker.get("source_paths") or [])
    required_api = {
        "apps/api/alembic/versions/0023_video_generation_runtime.py",
        "apps/api/src/lumi_api/generations/video_service.py",
        "apps/api/src/lumi_api/media_dispatch.py",
        "apps/api/src/lumi_api/persistence/models/video_generation.py",
    }
    required_worker = {
        "services/video-generation",
        "apps/worker-media/src/lumi_worker_media/cli.py",
        "apps/worker-media/src/lumi_worker_media/job_dispatch_runtime.py",
        "apps/worker-media/src/lumi_worker_media/event_runtime.py",
        "apps/worker-media/src/lumi_worker_media/external_wait_runtime.py",
        "apps/worker-media/src/lumi_worker_media/video_gateway_runtime.py",
        "apps/worker-media/src/lumi_worker_media/video_generation_repository.py",
        "apps/worker-media/src/lumi_worker_media/video_generation_runtime.py",
        "apps/worker-media/src/lumi_worker_media/video_sandbox_runtime.py",
        "apps/worker-media/src/lumi_worker_media/video_cost_runtime.py",
    }
    require(not (required_api - api_sources), "api runtime provenance omits Hosted video producer sources")
    require(not (required_worker - worker_sources), "worker runtime provenance omits outbox/video sources")


def main() -> None:
    service = read(VIDEO_SERVICE)
    gateway = read(GENERATION_GATEWAY)
    dispatch = read(MEDIA_DISPATCH)
    repository = read(VIDEO_REPOSITORY)
    outbox_cli = read(OUTBOX_CLI)
    job_dispatch = read(JOB_DISPATCH_RUNTIME)
    api_test = read(API_POSTGRES_TEST)
    outbox_test = read(OUTBOX_POSTGRES_TEST)
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
        outbox_cli,
        (
            'sub.add_parser("dispatch-outbox")',
            'dispatch.add_argument("--watch", action="store_true")',
            "MediaExternalWaitWakeScheduler(dsn)",
            "MediaJobOutboxDispatcher(dsn, CeleryJobPublisher())",
            'failures.append(("external-wake", exc))',
            'failures.append(("jobs", exc))',
            'raise RuntimeError(f"OUTBOX_DISPATCH_FAILED:{channels}")',
        ),
        "always-on outbox dispatcher CLI",
    )
    require_markers(
        job_dispatch,
        (
            "VIDEO_RENDER_TASK_NAME: (VIDEO_RENDER_QUEUE, VIDEO_RENDER_ROUTING_KEY)",
            "class MediaJobOutboxDispatcher",
            "celery_app.send_task(",
            "FOR UPDATE SKIP LOCKED",
            "SET published_at = now()",
        ),
        "canonical media outbox publisher",
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
        outbox_test,
        (
            "test_video_control_plane_outbox_reaches_canonical_dispatcher",
            "VideoGenerationControlPlane(session).create(",
            "MediaJobOutboxDispatcher(_dsn(), publisher)",
            'assert task_name == "lumi.jobs.video.render"',
            'assert queue == "lumi.media.video"',
            'assert row["published_at"] is not None',
            'assert row["publish_attempts"] == 1',
        ),
        "Video producer-to-dispatcher PostgreSQL acceptance",
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
            "apps/api/tests/integration/test_video_outbox_dispatch_postgres.py",
            "apps/worker-media/tests/integration/test_video_public_generation_sync_postgres.py",
            "Run Video Generation API PostgreSQL producer acceptance",
            "Run Hosted video PostgreSQL acceptance",
            "infra/iac/modules/compute/main.tf",
        ),
        "Video Generation workflow producer coverage",
    )

    validate_outbox_deployment()
    validate_runtime_provenance()
    print(
        "PASS: Hosted video generation has a canonical API producer, durable outbox "
        "publisher, always-on restricted dispatcher deployment, PostgreSQL acceptance, "
        "six-image provenance binding, and provider-neutral public state sync"
    )


if __name__ == "__main__":
    main()
