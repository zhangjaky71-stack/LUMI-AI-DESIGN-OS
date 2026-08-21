from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from uuid import UUID, uuid4

import asyncpg
import pytest
from lumi_video_generation.model import (
    CompiledShot,
    FinalVideoProvenance,
    RenderedVideo,
    ShotProvenance,
    ShotSpec,
    ShotValidationReport,
    StoredVideoClip,
    VideoTaskSpec,
)
from lumi_worker_media.video_generation_artifacts import PostgresVideoArtifactAdapter

pytestmark = pytest.mark.skipif(
    os.getenv("LUMI_DB_INTEGRATION") != "1",
    reason="set LUMI_DB_INTEGRATION=1 with migrated and seeded local PostgreSQL",
)

ORG = UUID("01900000-0000-7000-8000-000000000001")
PROJECT = UUID("01900000-0000-7000-8000-000000000006")


def _dsn() -> str:
    return os.environ["DATABASE_URL"].replace(
        "postgresql+asyncpg://", "postgresql://", 1
    )


def _spec() -> tuple[VideoTaskSpec, CompiledShot, UUID]:
    task_id = uuid4()
    paid_operation_id = uuid4()
    shot = ShotSpec(
        shot_id="hero",
        duration_seconds=Decimal("4"),
        prompt="Artifact replay acceptance",
    )
    spec = VideoTaskSpec(
        organization_id=str(ORG),
        project_id=str(PROJECT),
        task_id=str(task_id),
        operation_id=str(uuid4()),
        mode="TEXT_TO_VIDEO",
        prompt=shot.prompt,
        duration_seconds=Decimal("4"),
        aspect_ratio="16:9",
        width=1280,
        height=720,
        fps=24,
        budget_limit_usd=Decimal("5"),
        code_git_sha="c" * 40,
        shots=(shot,),
        recipe_version="video-artifact-replay-postgres-v1",
    )
    return (
        spec,
        CompiledShot(
            shot=shot,
            paid_operation_id=str(paid_operation_id),
            ordinal=1,
        ),
        paid_operation_id,
    )


def _clip(spec: VideoTaskSpec, paid_operation_id: UUID, checksum: str) -> StoredVideoClip:
    key = (
        f"generated/video/v1/{ORG}/{PROJECT}/shots/"
        f"{paid_operation_id.hex}/{checksum}.mp4"
    )
    return StoredVideoClip(
        storage_key=key,
        checksum_sha256=checksum,
        mime_type="video/mp4",
        size_bytes=4096,
        width=1280,
        height=720,
        duration_ms=4000,
        durable_asset_ref=key,
        poster_frame_ref=None,
        tail_frame_ref=None,
        keyframe_refs=(),
    )


def test_video_artifacts_are_deterministic_and_idempotent_across_replay() -> None:
    async def run() -> None:
        spec, shot, paid_operation_id = _spec()
        adapter = PostgresVideoArtifactAdapter(
            os.environ["DATABASE_URL"],
            bucket="lumi-assets",
        )
        validation = ShotValidationReport(decision="PASS", findings=())
        clip = _clip(spec, paid_operation_id, "d" * 64)
        video_job_id = f"video-job:{uuid4().hex}"
        shot_provenance = ShotProvenance(
            video_job_id=video_job_id,
            organization_id=str(ORG),
            shot_id="hero",
            paid_operation_id=str(paid_operation_id),
            storyboard_hash="b" * 64,
            prompt_hash="2" * 64,
            source_refs=(),
            continuity_refs=(),
            provider="openai",
            model="sora-2",
            provider_request_id=f"video_replay_{paid_operation_id.hex}",
            routing_reason_codes=("PROFILE_MATCH",),
            pricing_snapshot_id="sora-price-v1",
            cost_usd=Decimal("1.25000000"),
            cost_confidence="exact",
            brand_rule_set_version=None,
            identity_validation_snapshot_id=None,
            code_git_sha=spec.code_git_sha,
        )

        clip_first = await adapter.create_clip(
            spec=spec,
            shot=shot,
            clip=clip,
            provenance=shot_provenance,
            validation=validation,
            continuity_parent_version_ids=(),
        )
        clip_replay = await adapter.create_clip(
            spec=spec,
            shot=shot,
            clip=clip,
            provenance=shot_provenance,
            validation=validation,
            continuity_parent_version_ids=(),
        )
        assert clip_replay == clip_first

        final_clip = _clip(spec, paid_operation_id, "e" * 64)
        final_provenance = FinalVideoProvenance(
            video_job_id=video_job_id,
            organization_id=str(ORG),
            storyboard_hash="b" * 64,
            clip_artifact_version_ids=(clip_first,),
            timeline_hash="3" * 64,
            code_git_sha=spec.code_git_sha,
            brand_rule_set_version=None,
        )
        rendered = RenderedVideo(video=final_clip)
        final_first = await adapter.create_final(
            spec=spec,
            rendered=rendered,
            provenance=final_provenance,
            validation=validation,
            clip_artifact_version_ids=(clip_first,),
        )
        final_replay = await adapter.create_final(
            spec=spec,
            rendered=rendered,
            provenance=final_provenance,
            validation=validation,
            clip_artifact_version_ids=(clip_first,),
        )
        assert final_replay == final_first

        connection = await asyncpg.connect(_dsn())
        try:
            clip_version_count = await connection.fetchval(
                "SELECT count(*) FROM artifact_versions WHERE id=$1",
                UUID(clip_first),
            )
            final_version_count = await connection.fetchval(
                "SELECT count(*) FROM artifact_versions WHERE id=$1",
                UUID(final_first),
            )
            clip_file_count = await connection.fetchval(
                "SELECT count(*) FROM artifact_files WHERE artifact_version_id=$1",
                UUID(clip_first),
            )
            final_file_count = await connection.fetchval(
                "SELECT count(*) FROM artifact_files WHERE artifact_version_id=$1",
                UUID(final_first),
            )
            clip_provenance_count = await connection.fetchval(
                "SELECT count(*) FROM artifact_provenance WHERE artifact_version_id=$1",
                UUID(clip_first),
            )
            final_provenance_count = await connection.fetchval(
                "SELECT count(*) FROM artifact_provenance WHERE artifact_version_id=$1",
                UUID(final_first),
            )
            composed_edge_count = await connection.fetchval(
                """
                SELECT count(*) FROM artifact_edges
                WHERE organization_id=$1
                  AND from_artifact_version_id=$2
                  AND to_artifact_version_id=$3
                  AND edge_type='COMPOSED_FROM'
                """,
                ORG,
                UUID(clip_first),
                UUID(final_first),
            )
        finally:
            await connection.close()

        assert clip_version_count == 1
        assert final_version_count == 1
        assert clip_file_count == 1
        assert final_file_count == 1
        assert clip_provenance_count == 1
        assert final_provenance_count == 1
        assert composed_edge_count == 1

    asyncio.run(run())
