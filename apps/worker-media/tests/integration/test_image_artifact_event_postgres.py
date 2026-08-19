from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from uuid import UUID

import asyncpg
import pytest
from lumi_image_generation.model import (
    GenerationCandidate,
    GenerationProvenanceSnapshot,
    ImageGenerationSpec,
    OutputRequirements,
    StoredImage,
    ValidationBundle,
)
from lumi_worker_media.image_generation_artifacts import PostgresArtifactCandidateAdapter
from lumi_worker_media.image_generation_ports import PostgresGenerationEventSink

pytestmark = pytest.mark.skipif(
    os.getenv("LUMI_DB_INTEGRATION") != "1",
    reason="set LUMI_DB_INTEGRATION=1 with migrated and seeded local PostgreSQL",
)

ORG = "01900000-0000-7000-8000-000000000001"
PROJECT = "01900000-0000-7000-8000-000000000006"
TASK = "01900000-0000-7000-8000-000000000012"
OPERATION = "72900000-0000-7000-8000-000000000001"
VARIANT_OPERATION = "72900000-0000-7000-8000-000000000002"
GENERATION = "image-generation:" + "e" * 64
CANDIDATE = "image-candidate:" + "f" * 64
CHECKSUM = "a" * 64


def _dsn() -> str:
    value = os.environ["DATABASE_URL"]
    return value.replace("postgresql+asyncpg://", "postgresql://", 1)


def _spec() -> ImageGenerationSpec:
    return ImageGenerationSpec(
        organization_id=ORG,
        project_id=PROJECT,
        task_id=TASK,
        operation_id=OPERATION,
        purpose="artifact postgres acceptance",
        mode="TEXT_TO_IMAGE",
        prompt_compilation_ref="prompt:artifact-pg:v1",
        objective="Create product image",
        content="black coffee cup",
        visual_direction="minimal",
        aspect_ratio="1:1",
        target_width=1024,
        target_height=1024,
        variant_count=1,
        references=(),
        identity_requirements=(),
        brand_rule_set_version=None,
        constraints=(),
        quality_profile="HIGH",
        budget_limit_usd=Decimal("1.00"),
        output_requirements=OutputRequirements(format="PNG"),
        code_git_sha="b" * 40,
    )


def _stored() -> StoredImage:
    return StoredImage(
        storage_key=f"generated/v1/{ORG}/{PROJECT}/candidate/{CHECKSUM}.png",
        mime_type="image/png",
        width=1024,
        height=1024,
        size_bytes=4096,
        checksum_sha256=CHECKSUM,
    )


def _candidate() -> GenerationCandidate:
    return GenerationCandidate(
        candidate_id=CANDIDATE,
        generation_id=GENERATION,
        variant_index=1,
        status="VALIDATING",
        provider="openai",
        model="gpt-image-1.5",
        provider_request_id="req_artifact_pg_1",
        provider_output_ref=f"s3://lumi-assets/provider-output/v1/{ORG}/{OPERATION}/{CHECKSUM}.png",
        stored_image=_stored(),
    )


def _provenance() -> GenerationProvenanceSnapshot:
    return GenerationProvenanceSnapshot(
        generation_id=GENERATION,
        organization_id=ORG,
        project_id=PROJECT,
        task_id=TASK,
        operation_id=OPERATION,
        variant_operation_id=VARIANT_OPERATION,
        variant_index=1,
        provider="openai",
        model="gpt-image-1.5",
        model_revision=None,
        provider_request_id="req_artifact_pg_1",
        prompt_hash="c" * 64,
        prompt_template_version="test-v1",
        prompt_compilation_ref="prompt:artifact-pg:v1",
        reference_asset_refs=(),
        seed=None,
        width=1024,
        height=1024,
        quality_profile="HIGH",
        routing_reason_codes=("PROFILE_MATCH",),
        pricing_snapshot_id="image-price-v1",
        cost_usd=Decimal("0.12"),
        cost_confidence="exact",
        agent_run_id=None,
        recipe_version="recipe-v1",
        skill_versions={"image-generation": "v1"},
        code_git_sha="b" * 40,
        constraint_snapshot_hash="d" * 64,
        brand_rule_set_version=None,
        identity_validation_snapshot_id=None,
        safety_metadata={"blocked": False},
    )


async def _cleanup() -> None:
    connection = await asyncpg.connect(_dsn())
    try:
        async with connection.transaction():
            version_ids = await connection.fetch(
                """
                SELECT av.id
                FROM artifact_versions av
                JOIN artifacts a ON a.id = av.artifact_id
                WHERE a.organization_id=$1
                  AND a.project_id=$2
                  AND a.metadata_json ->> 'candidate_id' = $3
                """,
                UUID(ORG),
                UUID(PROJECT),
                CANDIDATE,
            )
            ids = [row["id"] for row in version_ids]
            if ids:
                await connection.execute(
                    "DELETE FROM artifact_provenance WHERE organization_id=$1 AND artifact_version_id = ANY($2::uuid[])",
                    UUID(ORG),
                    ids,
                )
                await connection.execute(
                    "DELETE FROM artifact_files WHERE organization_id=$1 AND artifact_version_id = ANY($2::uuid[])",
                    UUID(ORG),
                    ids,
                )
            await connection.execute(
                """
                UPDATE artifact_branches ab
                SET head_version_id=NULL
                FROM artifacts a
                WHERE ab.artifact_id=a.id
                  AND a.organization_id=$1
                  AND a.project_id=$2
                  AND a.metadata_json ->> 'candidate_id' = $3
                """,
                UUID(ORG),
                UUID(PROJECT),
                CANDIDATE,
            )
            await connection.execute(
                """
                DELETE FROM artifact_versions av
                USING artifacts a
                WHERE av.artifact_id=a.id
                  AND a.organization_id=$1
                  AND a.project_id=$2
                  AND a.metadata_json ->> 'candidate_id' = $3
                """,
                UUID(ORG),
                UUID(PROJECT),
                CANDIDATE,
            )
            await connection.execute(
                """
                DELETE FROM artifact_branches ab
                USING artifacts a
                WHERE ab.artifact_id=a.id
                  AND a.organization_id=$1
                  AND a.project_id=$2
                  AND a.metadata_json ->> 'candidate_id' = $3
                """,
                UUID(ORG),
                UUID(PROJECT),
                CANDIDATE,
            )
            await connection.execute(
                """
                DELETE FROM artifacts
                WHERE organization_id=$1
                  AND project_id=$2
                  AND metadata_json ->> 'candidate_id' = $3
                """,
                UUID(ORG),
                UUID(PROJECT),
                CANDIDATE,
            )
            await connection.execute(
                """
                DELETE FROM outbox_events
                WHERE organization_id=$1
                  AND aggregate_type='generation'
                  AND payload_json ->> 'generation_id' = $2
                """,
                UUID(ORG),
                GENERATION,
            )
    finally:
        await connection.close()


@pytest.fixture(autouse=True)
def cleanup() -> None:
    asyncio.run(_cleanup())
    yield
    asyncio.run(_cleanup())


def test_artifact_candidate_is_idempotent_and_uses_durable_generated_file() -> None:
    async def run() -> None:
        adapter = PostgresArtifactCandidateAdapter(
            os.environ["DATABASE_URL"],
            bucket="lumi-assets",
        )
        validation = ValidationBundle(findings=())
        first = await adapter.create_candidate(
            spec=_spec(),
            candidate=_candidate(),
            stored=_stored(),
            provenance=_provenance(),
            validation=validation,
        )
        second = await adapter.create_candidate(
            spec=_spec(),
            candidate=_candidate(),
            stored=_stored(),
            provenance=_provenance(),
            validation=validation,
        )
        assert second == first

        connection = await asyncpg.connect(_dsn())
        try:
            row = await connection.fetchrow(
                """
                SELECT a.kind, av.status, af.bucket, af.object_key, af.checksum_sha256,
                       ap.source_type, ap.operation
                FROM artifacts a
                JOIN artifact_versions av ON av.artifact_id=a.id
                JOIN artifact_files af ON af.artifact_version_id=av.id
                JOIN artifact_provenance ap ON ap.artifact_version_id=av.id
                WHERE a.id=$1 AND a.organization_id=$2
                """,
                UUID(first.artifact_id),
                UUID(ORG),
            )
        finally:
            await connection.close()
        assert row is not None
        assert row["kind"] == "RASTER_IMAGE"
        assert row["status"] == "ready"
        assert row["bucket"] == "lumi-assets"
        assert row["object_key"].startswith("generated/v1/")
        assert "provider-output/v1" not in row["object_key"]
        assert row["checksum_sha256"] == CHECKSUM
        assert row["source_type"] == "generation"
        assert row["operation"] == "image.generate"

    asyncio.run(run())


def test_generation_outbox_event_is_idempotent() -> None:
    async def run() -> None:
        sink = PostgresGenerationEventSink(os.environ["DATABASE_URL"])
        payload = {"status": "COMPLETED", "candidate_count": 1}
        await sink.emit(
            "generation.completed",
            organization_id=ORG,
            generation_id=GENERATION,
            payload=payload,
        )
        await sink.emit(
            "generation.completed",
            organization_id=ORG,
            generation_id=GENERATION,
            payload=payload,
        )
        connection = await asyncpg.connect(_dsn())
        try:
            rows = await connection.fetch(
                """
                SELECT event_type, payload_json
                FROM outbox_events
                WHERE organization_id=$1
                  AND aggregate_type='generation'
                  AND payload_json ->> 'generation_id' = $2
                """,
                UUID(ORG),
                GENERATION,
            )
        finally:
            await connection.close()
        assert len(rows) == 1
        assert rows[0]["event_type"] == "generation.completed"
        assert rows[0]["payload_json"]["candidate_count"] == 1

    asyncio.run(run())
