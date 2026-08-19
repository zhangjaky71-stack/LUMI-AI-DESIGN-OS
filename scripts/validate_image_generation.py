from __future__ import annotations

import json
from pathlib import Path
from typing import get_args

from lumi_image_generation.model import GenerationMode, ReferenceRole

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures/image-generation/node-46-conformance.json"
MODEL = ROOT / "services/image-generation/src/lumi_image_generation/model.py"
PORTS = ROOT / "services/image-generation/src/lumi_image_generation/ports.py"
PIPELINE = ROOT / "services/image-generation/src/lumi_image_generation/pipeline.py"
GATEWAY_ADAPTER = ROOT / "services/image-generation/src/lumi_image_generation/model_gateway_adapter.py"
ASSET_ADAPTER = ROOT / "services/image-generation/src/lumi_image_generation/asset_intelligence_adapter.py"
ARTIFACT_ADAPTER = ROOT / "services/image-generation/src/lumi_image_generation/artifact_adapter.py"
LEGACY_MIGRATION = ROOT / "db/migrations/0005_image_generation.sql"
WORKER_CODEC = ROOT / "apps/worker-media/src/lumi_worker_media/image_generation_codec.py"
WORKER_REPOSITORY = ROOT / "apps/worker-media/src/lumi_worker_media/image_generation_repository.py"
WORKER_GATEWAY = ROOT / "apps/worker-media/src/lumi_worker_media/image_gateway_runtime.py"
WORKER_PORTS = ROOT / "apps/worker-media/src/lumi_worker_media/image_generation_ports.py"
WORKER_ARTIFACTS = ROOT / "apps/worker-media/src/lumi_worker_media/image_generation_artifacts.py"
WORKER_RUNTIME = ROOT / "apps/worker-media/src/lumi_worker_media/image_generation_runtime.py"
WORKER_APP = ROOT / "apps/worker-media/src/lumi_worker_media/app.py"
WORKER_CLI = ROOT / "apps/worker-media/src/lumi_worker_media/worker_cli.py"
WORKER_DOCKERFILE = ROOT / "apps/worker-media/Dockerfile"
WORKFLOW_MODEL = ROOT / "apps/api/src/lumi_api/persistence/models/workflow.py"
WORKER_PROJECT = ROOT / "apps/worker-media/pyproject.toml"
WORKSPACE = ROOT / "pyproject.toml"

EXPECTED_MODES = {
    "TEXT_TO_IMAGE",
    "REFERENCE_TO_IMAGE",
    "PRODUCT_SCENE",
    "STYLE_REFERENCE",
    "TRANSPARENT_ASSET",
    "BACKGROUND_GENERATION",
    "COMPOSITION_EXPLORATION",
}
EXPECTED_ROLES = {"IDENTITY", "STYLE", "COMPOSITION", "CONTENT"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate_fixture() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assets = fixture["references"]
    require(set(fixture["modes"]) == EXPECTED_MODES, "fixture generation mode drift")
    require(set(fixture["reference_roles"]) == EXPECTED_ROLES, "fixture reference role drift")
    require(
        any(item.get("rights") == "UNKNOWN" for item in assets),
        "fixture requires UNKNOWN-rights denial case",
    )
    profiles = set(fixture["quality_benchmark_profiles"])
    require(
        {
            "chinese_poster_text_fidelity",
            "product_consistency",
            "brand_style",
            "multiple_aspect_ratios",
            "transparent_asset",
            "cost_latency",
            "fallback",
        }
        <= profiles,
        "quality benchmark coverage contract incomplete",
    )


def validate_python_contract() -> None:
    require(set(get_args(GenerationMode)) == EXPECTED_MODES, "GenerationMode contract drift")
    require(set(get_args(ReferenceRole)) == EXPECTED_ROLES, "ReferenceRole contract drift")

    model = MODEL.read_text(encoding="utf-8")
    ports = PORTS.read_text(encoding="utf-8")
    pipeline = PIPELINE.read_text(encoding="utf-8")
    gateway = GATEWAY_ADAPTER.read_text(encoding="utf-8")
    asset = ASSET_ADAPTER.read_text(encoding="utf-8")
    artifact = ARTIFACT_ADAPTER.read_text(encoding="utf-8")
    worker_codec = WORKER_CODEC.read_text(encoding="utf-8")
    worker_repository = WORKER_REPOSITORY.read_text(encoding="utf-8")
    worker_gateway = WORKER_GATEWAY.read_text(encoding="utf-8")
    worker_ports = WORKER_PORTS.read_text(encoding="utf-8")
    worker_artifacts = WORKER_ARTIFACTS.read_text(encoding="utf-8")
    worker_runtime = WORKER_RUNTIME.read_text(encoding="utf-8")
    worker_app = WORKER_APP.read_text(encoding="utf-8")
    worker_cli = WORKER_CLI.read_text(encoding="utf-8")
    worker_dockerfile = WORKER_DOCKERFILE.read_text(encoding="utf-8")
    workflow_model = WORKFLOW_MODEL.read_text(encoding="utf-8")

    require("budget_limit_usd: Decimal" in model, "generation budget must use Decimal")
    require("operation_id" in pipeline and "semantic_hash" in pipeline, "operation idempotency missing")
    require("await self.repository.get_by_operation" in pipeline, "async operation lookup missing")
    require("await self.repository.save_spec" in pipeline, "durable spec snapshot missing")
    require("await self.repository.save_pending" in pipeline, "durable pending snapshot missing")
    require("get_by_semantic" not in pipeline, "creative requests must not auto-cache by semantic hash")
    require("find_by_semantic" not in pipeline, "creative requests must not auto-cache by semantic hash")
    require("variant_operation_id=_variant_operation_id" in pipeline, "variant paid operation missing")
    require("resume_pending" in pipeline, "async resumability missing")
    require("validate_provider_image" in pipeline, "provider output integrity gate missing")
    require("def _raise_if_retryable" in pipeline, "transient generation retry propagation missing")
    require(
        'existing is not None and existing.status != "RUNNING"' in pipeline,
        "RUNNING generation retry/resume contract missing",
    )
    require("async def get_by_operation" in ports, "generation repository port must be async")
    require("async def save_pending" in ports, "pending repository port must be async")
    require("constraint_snapshot_hash(spec)" in artifact, "Artifact must bind full constraint snapshot")
    require("generation_provenance_snapshots" in artifact, "full generation provenance store missing")
    require("scoped_candidates" in asset, "references must use scope-first Asset Intelligence")
    require("commercial_use" in asset and "allowed_rights" in asset, "reference rights filtering missing")

    forbidden_provider_imports = (
        "import openai",
        "from openai",
        "import anthropic",
        "from anthropic",
        "import google.generativeai",
        "from google.generativeai",
        "import replicate",
        "from replicate",
    )
    core_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (MODEL, PORTS, PIPELINE, ASSET_ADAPTER, ARTIFACT_ADAPTER)
    ).casefold()
    for token in forbidden_provider_imports:
        require(token not in core_text, f"provider SDK leaked into generation domain: {token}")

    require("lumi_model_gateway" in gateway, "NODE-46 must route provider calls through Model Gateway")
    require("Capability.IMAGE_EDIT" not in gateway, "NODE-47 image.edit boundary violated")
    require("Capability.IMAGE_MASK_EDIT" not in gateway, "NODE-47 mask-edit boundary violated")

    require(
        "class PostgresGenerationRepository" in worker_repository,
        "hosted NODE-46 Postgres repository missing",
    )
    require(
        "FROM generations" in worker_repository
        and "INSERT INTO generations" in worker_repository,
        "hosted NODE-46 repository must use canonical generations table",
    )
    require(
        "image_generation_jobs" not in worker_repository
        and "image_generation_candidates" not in worker_repository,
        "hosted NODE-46 repository must not write legacy parallel generation tables",
    )
    require(
        "pg_advisory_xact_lock" in worker_repository,
        "same-operation generation writes require transactional advisory lock",
    )
    require(
        "GENERATION_OPERATION_SPEC_CONFLICT" in worker_repository,
        "durable repository semantic conflict guard missing",
    )
    require(
        "SNAPSHOT_SCHEMA_VERSION = 1" in worker_codec,
        "versioned generation JSON snapshot codec missing",
    )
    require(
        "GENERATION_SPEC_SEMANTIC_HASH_MISMATCH" in worker_codec,
        "generation snapshot semantic integrity check missing",
    )

    require(
        "class HostedImageModelGatewayAdapter" in worker_gateway
        and "HttpModelGatewayEstimateClient" in worker_gateway,
        "Worker Media must use private Model Gateway for image execution",
    )
    require(
        "ImageGenerationTransientError" in worker_gateway
        and "_TRANSIENT_HTTP_STATUSES" in worker_gateway,
        "private Model Gateway/S3 transient classification missing",
    )
    require(
        "provider-output/v1/" in worker_gateway,
        "Worker Media provider output fetcher must be bound to provider staging namespace",
    )
    for secret_marker in (
        "OPENAI_API_KEY",
        "LUMI_MODEL_PROVIDER_SECRET",
        "LUMI_MEDIA_PROVIDER_SECRET",
        "api.openai.com",
    ):
        require(
            secret_marker not in worker_gateway,
            f"provider boundary leaked into Worker Media: {secret_marker}",
        )

    require(
        "class PostgresReferenceAuthorizer" in worker_ports
        and "commercial_use" in worker_ports
        and "GENERATION_REFERENCE_RIGHTS_UNKNOWN" in worker_ports,
        "hosted reference-rights fail-closed adapter missing",
    )
    require(
        "class S3GeneratedImageStore" in worker_ports
        and 'f"generated/v1/' in worker_ports
        and "GENERATION_STORAGE_TEMPORARY" in worker_ports,
        "durable generated-image storage/retry boundary missing",
    )
    require(
        "class PostgresGenerationCostObserver" in worker_ports
        and "FROM cost_ledger" in worker_ports,
        "NODE-27 generation cost observer missing",
    )
    require(
        "INSERT INTO cost_ledger" not in worker_ports,
        "Worker Media must never duplicate Model Gateway provider cost writes",
    )
    require(
        "class PostgresGenerationEventSink" in worker_ports
        and "INSERT INTO outbox_events" in worker_ports,
        "canonical generation outbox sink missing",
    )

    for table in (
        "artifacts",
        "artifact_branches",
        "artifact_versions",
        "artifact_files",
        "artifact_provenance",
    ):
        require(
            f"INSERT INTO {table}" in worker_artifacts,
            f"hosted artifact adapter must write canonical {table}",
        )
    require(
        'stored.storage_key.startswith("generated/v1/")' in worker_artifacts,
        "Artifact files must reference durable generated images, not provider staging",
    )

    require(
        "class HostedImageGenerationRuntime" in worker_runtime,
        "hosted NODE-46 composition root missing",
    )
    for marker in (
        "PostgresGenerationRepository",
        "PostgresReferenceAuthorizer",
        "HostedImageModelGatewayAdapter",
        "S3ProviderOutputFetcher",
        "S3GeneratedImageStore",
        "PostgresArtifactCandidateAdapter",
        "PostgresGenerationCostObserver",
        "PostgresGenerationEventSink",
    ):
        require(marker in worker_runtime, f"hosted image composition missing {marker}")
    require(
        "_ClassifyingS3ObjectStore" in worker_runtime
        and "_TRANSIENT_S3_HTTP_STATUSES" in worker_runtime
        and "_PERMANENT_S3_ERROR_CODES" in worker_runtime
        and "GENERATION_STORAGE_S3_REJECTED" in worker_runtime,
        "hosted durable S3 transient/permanent retry boundary missing",
    )
    require(
        "SELECT type, input_json" in worker_runtime and "SELECT task_type" not in worker_runtime,
        "hosted image runtime must read canonical tasks.type",
    )
    require(
        "image_generation_spec" in worker_runtime
        and "IMAGE_GENERATION_TASK_OPERATION_MISMATCH" in worker_runtime,
        "task DB snapshot/scope validation missing",
    )

    image_task_block = worker_app.split("def image_transform", 1)[1].split(
        '@celery_app.task(name="lumi.jobs.video.render"', 1
    )[0]
    require(
        '"status": "accepted"' not in image_task_block,
        "image.transform must not regress to accepted-only placeholder",
    )
    require(
        "HostedImageGenerationRuntime" in worker_app
        and "TaskJobStore" in worker_app
        and "execute_job" in worker_app,
        "Celery image.transform must enter durable NODE-46 runtime",
    )
    require(
        "JobState.RETRYING" in image_task_block and "JobState.FAILED" in image_task_block,
        "Celery image task retry/failure propagation missing",
    )

    require(
        "celery_app.worker_main" in worker_cli
        and "QUEUE_BY_JOB_KIND" in worker_cli
        and "LUMI_WORKER_MEDIA_CONCURRENCY" in worker_cli,
        "production Worker Media Celery entrypoint missing or unconstrained",
    )
    require(
        "uv sync --all-packages --frozen --no-dev" in worker_dockerfile,
        "Worker Media image must use canonical frozen all-workspace install",
    )
    require("USER 10001:10001" in worker_dockerfile, "Worker Media image must run non-root")
    require(
        'CMD ["python", "-m", "lumi_worker_media.worker_cli"]' in worker_dockerfile,
        "Worker Media image must start the production Celery entrypoint",
    )

    generation_block = workflow_model.split("class Generation(", 1)[1].split(
        "class ProviderRequest(", 1
    )[0]
    require(
        'status: Mapped[str] = mapped_column(String(32)' in generation_block,
        "canonical generations.status storage contract missing",
    )
    require(
        "CheckConstraint" not in generation_block,
        "canonical generations.status must remain open to NODE-46 lifecycle states",
    )


def validate_workspace_contract() -> None:
    workspace = WORKSPACE.read_text(encoding="utf-8")
    worker = WORKER_PROJECT.read_text(encoding="utf-8")
    require(
        '"services/image-generation"' in workspace,
        "image-generation must be a canonical uv workspace member",
    )
    require(
        "lumi-image-generation = { workspace = true }" in workspace,
        "image-generation workspace source mapping missing",
    )
    for dependency in (
        '"asyncpg==0.31.0"',
        '"lumi-image-generation"',
        '"lumi-model-gateway"',
    ):
        require(dependency in worker, f"Worker Media direct dependency missing: {dependency}")


def validate_legacy_sql_boundary() -> None:
    sql = LEGACY_MIGRATION.read_text(encoding="utf-8")
    require(
        "LEGACY_REFERENCE_ONLY: DO NOT APPLY TO STAGING OR PRODUCTION" in sql,
        "legacy parallel NODE-46 SQL must be explicitly non-production",
    )
    require(
        "Release gates MUST NOT apply this file" in sql,
        "legacy NODE-46 SQL must forbid release-gate application",
    )


def main() -> None:
    validate_fixture()
    validate_python_contract()
    validate_workspace_contract()
    validate_legacy_sql_boundary()
    print("NODE-46 image generation architecture contract: OK")


if __name__ == "__main__":
    main()
