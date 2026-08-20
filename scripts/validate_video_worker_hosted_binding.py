#!/usr/bin/env python3
from __future__ import annotations

import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER_APP = ROOT / "apps/worker-media/src/lumi_worker_media/app.py"
WORKER_PROJECT = ROOT / "apps/worker-media/pyproject.toml"
HOSTED_RUNTIME = ROOT / "apps/worker-media/src/lumi_worker_media/video_generation_runtime.py"
VIDEO_COST = ROOT / "apps/worker-media/src/lumi_worker_media/video_cost_runtime.py"
VIDEO_GATEWAY = ROOT / "apps/worker-media/src/lumi_worker_media/video_gateway_runtime.py"
VIDEO_REPOSITORY = ROOT / "apps/worker-media/src/lumi_worker_media/video_generation_repository.py"
VIDEO_ARTIFACT = ROOT / "apps/worker-media/src/lumi_worker_media/video_generation_artifacts.py"
VIDEO_PORTS = ROOT / "apps/worker-media/src/lumi_worker_media/video_generation_ports.py"
VIDEO_SANDBOX = ROOT / "apps/worker-media/src/lumi_worker_media/video_sandbox_runtime.py"
VIDEO_CODEC = ROOT / "apps/worker-media/src/lumi_worker_media/video_generation_codec.py"
VIDEO_MIGRATION = ROOT / "apps/api/alembic/versions/0023_video_generation_runtime.py"
VIDEO_COST_TEST = ROOT / "apps/worker-media/tests/test_video_cost_runtime.py"
VIDEO_GATEWAY_TEST = ROOT / "apps/worker-media/tests/test_video_gateway_runtime.py"
VIDEO_PORTS_TEST = ROOT / "apps/worker-media/tests/test_video_generation_ports.py"
VIDEO_SANDBOX_TEST = ROOT / "apps/worker-media/tests/test_video_sandbox_runtime.py"
VIDEO_POSTGRES_TEST = ROOT / "apps/worker-media/tests/integration/test_video_hosted_postgres.py"
VIDEO_PRIVILEGE_TEST = ROOT / "apps/worker-media/tests/integration/test_video_runtime_privileges_postgres.py"
PROVIDER_OUTPUT = ROOT / "apps/api/src/lumi_api/provider_output_store.py"
PROVIDER_OUTPUT_TEST = ROOT / "apps/api/tests/test_provider_output_store.py"
VIDEO_PERFORMANCE = ROOT / "services/video-generation/src/lumi_video_generation/performance_ports.py"
VIDEO_WORKFLOW = ROOT / ".github/workflows/video-generation.yml"
VIDEO_PRODUCER_GATE = ROOT / "scripts/validate_video_generation_producer_binding.py"
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


def read(path: Path) -> str:
    require(path.is_file(), f"missing {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


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


def validate_iac() -> None:
    for environment in ENVIRONMENTS:
        main = read(ROOT / f"infra/iac/environments/{environment}/app/main.tf")
        variables = read(ROOT / f"infra/iac/environments/{environment}/app/variables.tf")
        tfvars = read(
            ROOT / f"infra/iac/environments/{environment}/app/terraform.tfvars.example"
        )
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
            f"{environment} video profile example",
        )


def main() -> None:
    worker = read(WORKER_APP)
    project = read(WORKER_PROJECT)
    hosted = read(HOSTED_RUNTIME)
    cost = read(VIDEO_COST)
    gateway = read(VIDEO_GATEWAY)
    repository = read(VIDEO_REPOSITORY)
    artifact = read(VIDEO_ARTIFACT)
    ports = read(VIDEO_PORTS)
    sandbox = read(VIDEO_SANDBOX)
    codec = read(VIDEO_CODEC)
    migration = read(VIDEO_MIGRATION)
    cost_test = read(VIDEO_COST_TEST)
    gateway_test = read(VIDEO_GATEWAY_TEST)
    ports_test = read(VIDEO_PORTS_TEST)
    sandbox_test = read(VIDEO_SANDBOX_TEST)
    postgres_test = read(VIDEO_POSTGRES_TEST)
    privilege_test = read(VIDEO_PRIVILEGE_TEST)
    provider_output = read(PROVIDER_OUTPUT)
    provider_output_test = read(PROVIDER_OUTPUT_TEST)
    performance = read(VIDEO_PERFORMANCE)
    workflow = read(VIDEO_WORKFLOW)
    sandbox_workflow = read(SANDBOX_WORKFLOW)

    require("lumi-video-generation" in project, "Worker Media lacks video-generation dependency")
    require("lumi-asset-storage" in project, "Worker Media lacks asset-storage dependency")

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
    video_block = worker.split('name="lumi.jobs.video.render"', 1)[1].split(
        "@celery_app.task", 1
    )[0]
    require('"status": "accepted"' not in video_block, "video.render is accepted-only")

    require_markers(
        hosted,
        (
            "HostedVideoGenerationRuntime",
            "PostgresVideoRepository",
            "HostedVideoGateway.from_env()",
            "HostedVideoOutputAdapter.from_env()",
            "HostedVideoMediaSandbox.from_spec(spec)",
            "PostgresVideoArtifactAdapter",
            "ScopedPostgresVideoCostObserver",
            "costs=ScopedPostgresVideoCostObserver(self.database_dsn)",
            "PostgresVideoEventSink",
            "TimedMediaSandbox",
            "PerformanceTelemetryContext.from_environ()",
            "ExternalWait(",
            'wait_reason="video_provider_pending"',
            "LUMI_VIDEO_MODEL_PROFILE",
        ),
        "hosted video composition",
    )
    forbid_markers(
        hosted,
        (
            "InMemoryVideoRepository",
            "ArtifactHistoryVideoAdapter",
            "MemoryMediaSandbox",
            "costs=PostgresVideoCostObserver(",
        ),
        "hosted video composition",
    )

    require_markers(
        cost,
        (
            "class ScopedPostgresVideoCostObserver",
            "FROM video_generation_jobs",
            "job_snapshot ->> 'video_job_id' = $1",
            "VIDEO_COST_JOB_SCOPE_NOT_UNIQUE",
            "io.organization_id = cl.organization_id",
            "cl.organization_id = $1",
            "io.organization_id = $1",
            "io.business_scope_id = $2",
            "confidence.casefold()",
        ),
        "tenant-scoped video cost observer",
    )
    forbid_markers(
        cost,
        ("INSERT INTO cost_ledger", "UPDATE cost_ledger", "DELETE FROM cost_ledger"),
        "tenant-scoped video cost observer",
    )
    require_markers(
        cost_test,
        (
            "test_video_cost_reconciliation_is_tenant_scoped",
            "test_video_cost_duplicate_job_scope_fails_before_ledger_lookup",
            "test_video_cost_confidence_uses_canonical_lowercase_ledger_contract",
        ),
        "video cost executable coverage",
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
        ),
        "hosted video gateway tests",
    )

    require_markers(
        repository,
        (
            "class PostgresVideoRepository",
            "video_generation_jobs",
            "video_provider_jobs",
            "pg_advisory_xact_lock",
        ),
        "durable video repository",
    )
    forbid_markers(
        repository,
        ("DELETE FROM video_generation_jobs", "DELETE FROM video_provider_jobs"),
        "durable video repository",
    )
    require_markers(
        artifact,
        (
            "class PostgresVideoArtifactAdapter",
            "artifact_versions",
            "artifact_edges",
            "COMPOSED_FROM",
        ),
        "durable video artifact adapter",
    )
    require_markers(
        ports,
        (
            "class HostedVideoOutputAdapter",
            "provider-output/v1/async/",
            "sandbox-exchange/v1/",
            "class HostedVideoMediaSandbox",
            "TypedFfmpegSandbox",
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
        "hosted video ports tests",
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
        "worker sandbox exchange",
    )
    require_markers(
        sandbox_test,
        (
            "test_exchange_manifest_and_promotion_use_server_side_copy",
            "test_input_stage_checksum_mismatch_fails_closed",
            "test_sandbox_bridge_rejects_network_enabled_invocation",
        ),
        "worker sandbox tests",
    )

    require_markers(
        provider_output,
        (
            "store_async_path",
            "_sha256_path(path, max_bytes=max_bytes)",
            "checksum_sha256_b64=_sha256_b64(digest)",
        ),
        "provider output staging",
    )
    require_markers(
        provider_output_test,
        (
            "test_async_video_path_uses_existing_s3_checksum_contract",
            "test_video_path_size_bound_fails_before_s3_upload",
            'self.assertNotIn("max_bytes", call)',
        ),
        "provider output tests",
    )
    require_markers(
        codec,
        ("encode_video_task_spec", "decode_video_task_spec"),
        "durable video codec",
    )
    require_markers(
        performance,
        ("class TimedMediaSandbox", "PerformanceStage.POSTPROCESS"),
        "video postprocess telemetry",
    )

    require_markers(
        migration,
        (
            'revision = "0023_video_generation_runtime"',
            "CREATE TABLE video_generation_jobs",
            "CREATE TABLE video_provider_jobs",
            "GRANT SELECT, INSERT, UPDATE ON video_generation_jobs, video_provider_jobs TO lumi_app",
        ),
        "Hosted video Alembic",
    )
    forbid_markers(
        migration,
        (
            "GRANT SELECT, INSERT, UPDATE, DELETE ON video_generation_jobs",
            "GRANT DELETE ON video_generation_jobs",
            "GRANT DELETE ON video_provider_jobs",
        ),
        "Hosted video Alembic",
    )

    require_markers(
        postgres_test,
        (
            "test_video_repository_round_trip_preserves_external_provider_identity",
            "test_cost_outbox_artifact_and_external_wait_recovery_use_canonical_postgres",
            "PostgresVideoRepository",
            "ScopedPostgresVideoCostObserver",
            "PostgresVideoArtifactAdapter",
            "PostgresVideoEventSink",
            "MediaExternalWaitWakeScheduler",
            "TaskJobStore",
            "unique identities",
            'assert edge["edge_type"] == "COMPOSED_FROM"',
            "assert dispatch_count == 2",
            "assert cost_count == 1",
        ),
        "Hosted video PostgreSQL acceptance",
    )
    forbid_markers(
        postgres_test,
        (
            "DELETE FROM cost_ledger",
            "DELETE FROM artifact_edges",
            "DELETE FROM artifact_files",
            "DELETE FROM artifact_provenance",
        ),
        "Hosted video PostgreSQL append-only acceptance",
    )
    require_markers(
        privilege_test,
        (
            "test_video_runtime_privileges_preserve_durable_history",
            "has_table_privilege",
            "video_generation_jobs",
            "video_provider_jobs",
            "cost_ledger",
            "artifact_edges",
            "artifact_files",
            "artifact_provenance",
            "assert immutable == 4",
        ),
        "Hosted video privilege acceptance",
    )

    require_markers(
        workflow,
        (
            "scripts/validate_video_worker_hosted_binding.py",
            "apps/worker-media/tests/integration/test_video_*.py",
            "apps/worker-media/tests/integration/test_video_hosted_postgres.py",
            "apps/worker-media/tests/integration/test_video_runtime_privileges_postgres.py",
            "Run Hosted video PostgreSQL acceptance",
            "uv sync --all-packages --frozen",
            "historical parallel NODE-48 tables are absent",
            "CONFIRM=1 make infra-reset",
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

    require(VIDEO_PRODUCER_GATE.is_file(), "missing Hosted video generation producer gate")
    runpy.run_path(str(VIDEO_PRODUCER_GATE), run_name="__main__")
    validate_iac()
    print(
        "PASS: Hosted video.render production binding is durable, tenant-scoped, "
        "append-only, PostgreSQL-accepted, isolated, checksum-bound, and CI-gated"
    )


if __name__ == "__main__":
    main()
