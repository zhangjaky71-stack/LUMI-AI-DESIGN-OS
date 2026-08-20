#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER_APP = ROOT / "apps/worker-media/src/lumi_worker_media/app.py"
WORKER_PROJECT = ROOT / "apps/worker-media/pyproject.toml"
HOSTED_RUNTIME = ROOT / "apps/worker-media/src/lumi_worker_media/video_generation_runtime.py"
VIDEO_GATEWAY = ROOT / "apps/worker-media/src/lumi_worker_media/video_gateway_runtime.py"
VIDEO_REPOSITORY = ROOT / "apps/worker-media/src/lumi_worker_media/video_generation_repository.py"
VIDEO_ARTIFACT = ROOT / "apps/worker-media/src/lumi_worker_media/video_generation_artifacts.py"
VIDEO_PORTS = ROOT / "apps/worker-media/src/lumi_worker_media/video_generation_ports.py"
VIDEO_SANDBOX = ROOT / "apps/worker-media/src/lumi_worker_media/video_sandbox_runtime.py"
VIDEO_CODEC = ROOT / "apps/worker-media/src/lumi_worker_media/video_generation_codec.py"
VIDEO_GATEWAY_TEST = ROOT / "apps/worker-media/tests/test_video_gateway_runtime.py"
VIDEO_PORTS_TEST = ROOT / "apps/worker-media/tests/test_video_generation_ports.py"
VIDEO_SANDBOX_TEST = ROOT / "apps/worker-media/tests/test_video_sandbox_runtime.py"
PROVIDER_OUTPUT = ROOT / "apps/api/src/lumi_api/provider_output_store.py"
PROVIDER_OUTPUT_TEST = ROOT / "apps/api/tests/test_provider_output_store.py"
VIDEO_PERFORMANCE = ROOT / "services/video-generation/src/lumi_video_generation/performance_ports.py"
VIDEO_WORKFLOW = ROOT / ".github/workflows/video-generation.yml"
SANDBOX_WORKFLOW = ROOT / ".github/workflows/sandbox-remote-runtime-closure.yml"
ENVIRONMENTS = ("staging", "production")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"BLOCK: {message}")


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
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise SystemExit(f"BLOCK: unterminated Terraform service block: {service}")


def validate_iac() -> None:
    for environment in ENVIRONMENTS:
        main_path = ROOT / f"infra/iac/environments/{environment}/app/main.tf"
        variables_path = ROOT / f"infra/iac/environments/{environment}/app/variables.tf"
        tfvars_path = ROOT / f"infra/iac/environments/{environment}/app/terraform.tfvars.example"
        for path in (main_path, variables_path, tfvars_path):
            require(path.is_file(), f"missing {path.relative_to(ROOT)}")
        main = main_path.read_text(encoding="utf-8")
        variables = variables_path.read_text(encoding="utf-8")
        tfvars = tfvars_path.read_text(encoding="utf-8")
        worker = service_block(main, "worker-media")
        require_markers(
            worker,
            (
                "local.model_gateway_environment",
                "local.sandbox_runtime_environment",
                'LUMI_VIDEO_MODEL_PROFILE     = var.video_model_profile',
                'LUMI_SANDBOX_EXCHANGE_BUCKET = local.bucket_names["sandbox"]',
                'LUMI_MODEL_GATEWAY_AUTH_SECRET   = local.secret_arns["internal/model-gateway"]',
                'LUMI_SANDBOX_RUNTIME_AUTH_SECRET = local.secret_arns["internal/sandbox-runtime"]',
                'local.bucket_arns["assets"]',
                'local.bucket_arns["sandbox"]',
            ),
            f"{environment} worker-media IaC",
        )
        forbid_markers(
            worker,
            (
                "LUMI_MODEL_PROVIDER_SECRET",
                "LUMI_MEDIA_PROVIDER_SECRET",
                'local.secret_arns["providers/model"]',
                'local.secret_arns["providers/media"]',
            ),
            f"{environment} worker-media IaC",
        )
        require_markers(
            variables,
            (
                'variable "video_model_profile"',
                'regex("^[A-Za-z0-9][A-Za-z0-9_.+-]{0,99}$", var.video_model_profile)',
            ),
            f"{environment} video profile variable",
        )
        require_markers(
            tfvars,
            (
                "video_models[*].profiles",
                'video_model_profile = "REPLACE_WITH_MEDIA_SECRET_VIDEO_PROFILE"',
            ),
            f"{environment} tfvars video profile example",
        )


def main() -> None:
    required_files = (
        WORKER_APP,
        WORKER_PROJECT,
        HOSTED_RUNTIME,
        VIDEO_GATEWAY,
        VIDEO_REPOSITORY,
        VIDEO_ARTIFACT,
        VIDEO_PORTS,
        VIDEO_SANDBOX,
        VIDEO_CODEC,
        VIDEO_GATEWAY_TEST,
        VIDEO_PORTS_TEST,
        VIDEO_SANDBOX_TEST,
        PROVIDER_OUTPUT,
        PROVIDER_OUTPUT_TEST,
        VIDEO_PERFORMANCE,
        VIDEO_WORKFLOW,
        SANDBOX_WORKFLOW,
    )
    for path in required_files:
        require(path.is_file(), f"missing {path.relative_to(ROOT)}")

    worker = WORKER_APP.read_text(encoding="utf-8")
    project = WORKER_PROJECT.read_text(encoding="utf-8")
    hosted = HOSTED_RUNTIME.read_text(encoding="utf-8")
    gateway = VIDEO_GATEWAY.read_text(encoding="utf-8")
    repository = VIDEO_REPOSITORY.read_text(encoding="utf-8")
    artifact = VIDEO_ARTIFACT.read_text(encoding="utf-8")
    ports = VIDEO_PORTS.read_text(encoding="utf-8")
    sandbox = VIDEO_SANDBOX.read_text(encoding="utf-8")
    codec = VIDEO_CODEC.read_text(encoding="utf-8")
    gateway_test = VIDEO_GATEWAY_TEST.read_text(encoding="utf-8")
    ports_test = VIDEO_PORTS_TEST.read_text(encoding="utf-8")
    sandbox_test = VIDEO_SANDBOX_TEST.read_text(encoding="utf-8")
    provider_output = PROVIDER_OUTPUT.read_text(encoding="utf-8")
    provider_output_test = PROVIDER_OUTPUT_TEST.read_text(encoding="utf-8")
    performance = VIDEO_PERFORMANCE.read_text(encoding="utf-8")
    workflow = VIDEO_WORKFLOW.read_text(encoding="utf-8")
    sandbox_workflow = SANDBOX_WORKFLOW.read_text(encoding="utf-8")

    require("lumi-video-generation" in project, "Worker Media does not depend on video-generation package")
    require("lumi-asset-storage" in project, "Worker Media does not depend on asset-storage package")

    require_markers(
        worker,
        (
            "HostedVideoGenerationRuntime",
            "_execute_video_generation_job",
            "execute_job(",
            'name="lumi.jobs.video.render"',
            "JobState.RETRYING",
            "JobState.FAILED",
        ),
        "worker video.render lifecycle",
    )
    video_block = worker.split('name="lumi.jobs.video.render"', 1)[1].split("@celery_app.task", 1)[0]
    require('"status": "accepted"' not in video_block, "video.render still returns accepted-only placeholder")

    require_markers(
        hosted,
        (
            "HostedVideoGenerationRuntime",
            "PostgresVideoRepository",
            "HostedVideoGateway.from_env()",
            "HostedVideoOutputAdapter.from_env()",
            "HostedVideoMediaSandbox.from_spec(spec)",
            "PostgresVideoArtifactAdapter",
            "PostgresVideoCostObserver",
            "PostgresVideoEventSink",
            "TimedMediaSandbox",
            "PerformanceTelemetryContext.from_environ()",
            "ExternalWait(",
            'wait_reason="video_provider_pending"',
            'LUMI_VIDEO_MODEL_PROFILE',
        ),
        "hosted video composition root",
    )
    forbid_markers(
        hosted,
        ("InMemoryVideoRepository", "ArtifactHistoryVideoAdapter", "MemoryMediaSandbox"),
        "hosted video composition root",
    )

    require_markers(
        gateway,
        (
            'profile = os.getenv("LUMI_VIDEO_MODEL_PROFILE", "")',
            'caller_service="worker-media"',
            'constraints["model_profile"] = self.model_profile',
            "VIDEO_HOSTED_V1_NEGATIVE_PROMPT_UNSUPPORTED",
            "VIDEO_HOSTED_V1_SEED_UNSUPPORTED",
            "VIDEO_HOSTED_V1_CAMERA_MOTION_UNSUPPORTED",
            "VIDEO_HOSTED_V1_SUBJECT_ACTION_UNSUPPORTED",
        ),
        "hosted video gateway",
    )
    require_markers(
        gateway_test,
        (
            "test_hosted_video_request_binds_explicit_model_profile",
            "test_hosted_video_rejects_controls_not_supported_by_provider_create_api",
            "VIDEO_HOSTED_V1_NEGATIVE_PROMPT_UNSUPPORTED",
            "VIDEO_HOSTED_V1_CAMERA_MOTION_UNSUPPORTED",
        ),
        "hosted video gateway executable coverage",
    )

    require_markers(
        repository,
        ("class PostgresVideoRepository", "video_generation_jobs", "video_provider_jobs"),
        "durable video repository",
    )
    require_markers(
        artifact,
        ("class PostgresVideoArtifactAdapter", "artifact_versions", "COMPOSED_FROM"),
        "durable video artifact adapter",
    )
    require_markers(
        ports,
        (
            "class HostedVideoOutputAdapter",
            'provider-output/v1/async/',
            'sandbox-exchange/v1/',
            "class HostedVideoMediaSandbox",
            "TypedFfmpegSandbox",
            "class PostgresVideoCostObserver",
            "cost_ledger",
            "class PostgresVideoEventSink",
            "event_name",
            "schema_version",
        ),
        "hosted video ports",
    )
    require_markers(
        ports_test,
        (
            "test_provider_output_is_probed_in_exchange_then_promoted_by_server_side_copy",
            "test_provider_output_wrong_bucket_fails_before_s3",
            "test_durable_promotion_checksum_drift_fails_closed",
        ),
        "hosted video ports executable coverage",
    )
    require_markers(
        sandbox,
        (
            "class SandboxExchangeMediaRuntime",
            "object_store.copy(",
            '"exchange_inputs"',
            '"exchange_outputs"',
            "network_disabled",
            "VIDEO_SANDBOX_STAGE_CHECKSUM_MISMATCH",
            "VIDEO_SANDBOX_DURABLE_PROMOTION_MISMATCH",
        ),
        "worker sandbox exchange bridge",
    )
    require_markers(
        sandbox_test,
        (
            "test_exchange_manifest_and_promotion_use_server_side_copy",
            "test_input_stage_checksum_mismatch_fails_closed",
            "test_sandbox_bridge_rejects_network_enabled_invocation",
        ),
        "worker sandbox exchange executable coverage",
    )
    require_markers(
        provider_output,
        (
            "store_async_path",
            "_sha256_path(path, max_bytes=max_bytes)",
            "checksum_sha256_b64=_sha256_b64(digest)",
        ),
        "provider video output staging",
    )
    require_markers(
        provider_output_test,
        (
            "test_async_video_path_uses_existing_s3_checksum_contract",
            "test_video_path_size_bound_fails_before_s3_upload",
            'self.assertNotIn("max_bytes", call)',
        ),
        "provider output executable coverage",
    )
    require_markers(
        codec,
        ("encode_video_task_spec", "decode_video_task_spec"),
        "durable video spec codec",
    )
    require_markers(
        performance,
        ("class TimedMediaSandbox", "PerformanceStage.POSTPROCESS"),
        "video postprocess telemetry",
    )

    require_markers(
        workflow,
        (
            "scripts/validate_video_worker_hosted_binding.py",
            "apps/worker-media/src/lumi_worker_media/video_*.py",
            "apps/worker-media/tests/test_video_*.py",
            "apps/api/tests/test_provider_output_store.py",
            "uv sync --all-packages --frozen",
            "historical parallel NODE-48 tables are absent",
        ),
        "video generation workflow",
    )
    require_markers(
        sandbox_workflow,
        (
            "services/sandbox-runtime/tests/test_exchange_file_runtime.py",
            "Execute exchange file fail-closed contract",
        ),
        "sandbox exchange workflow",
    )

    validate_iac()
    print("PASS: Hosted video.render production binding is durable, isolated, checksum-bound, and CI-gated")


if __name__ == "__main__":
    main()
