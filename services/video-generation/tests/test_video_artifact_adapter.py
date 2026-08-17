from __future__ import annotations

import asyncio
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from uuid import UUID, uuid4

from lumi_api.artifact_engine.service import ArtifactEngineService
from lumi_api.artifacts.models import ArtifactType, LineageEdgeType
from lumi_api.video_generation.artifact_adapter import Node42VideoArtifactAdapter
from lumi_video_generation.model import (
    CompiledShot,
    DurableVideoObject,
    FinalVideoProvenance,
    RenderedVideo,
    ShotProvenance,
    ShotRuntime,
    ShotSpec,
    ShotStatus,
    SourceImageRef,
    StoredVideoClip,
    VideoJob,
    VideoJobStatus,
    VideoMode,
    VideoProbeResult,
    VideoTaskSpec,
)


class FakeArtifactService:
    def __init__(self) -> None:
        self.commands = []
        self._version_artifacts: dict[UUID, UUID] = {}

    def create_artifact(self, command):
        artifact_id = uuid4()
        version_id = uuid4()
        self.commands.append(command)
        self._version_artifacts[version_id] = artifact_id
        return (
            SimpleNamespace(id=artifact_id),
            SimpleNamespace(head_version_id=version_id),
        )

    def mark_ready(self, version_id, *, occurred_at):
        return SimpleNamespace(
            id=version_id,
            artifact_id=self._version_artifacts[version_id],
        )


def _fixture():
    source = SourceImageRef(
        asset_id="11111111-1111-4111-8111-111111111111",
        asset_version="v1",
        durable_ref="asset:source:v1",
        checksum_sha256="a" * 64,
        rights_snapshot_id="rights-v1",
    )
    shot = ShotSpec(
        shot_id="hero",
        duration_seconds=Decimal("4"),
        prompt="Slow product orbit",
        source_ref=source,
    )
    spec = VideoTaskSpec(
        organization_id="22222222-2222-4222-8222-222222222222",
        project_id="33333333-3333-4333-8333-333333333333",
        task_id="44444444-4444-4444-8444-444444444444",
        operation_id="55555555-5555-4555-8555-555555555555",
        mode=VideoMode.PRODUCT_MOTION,
        width=1280,
        height=720,
        fps=30,
        shots=(shot,),
        recipe_id="campaign-video-v1",
        skill_refs=("storyboard@1",),
        git_commit="d" * 40,
        user_use_declaration="commercial campaign",
    )
    compiled = CompiledShot(
        index=0,
        shot=shot,
        paid_operation_id="66666666-6666-4666-8666-666666666666",
    )
    probe = VideoProbeResult(
        mime_type="video/mp4",
        width=1280,
        height=720,
        duration_seconds=Decimal("4"),
        decodable_frames=120,
    )
    clip = StoredVideoClip(
        shot_id="hero",
        object=DurableVideoObject(
            durable_ref="asset:video:hero",
            bucket="generated-video",
            storage_key="video/hero.mp4",
            size_bytes=1024,
        ),
        checksum_sha256="b" * 64,
        probe=probe,
        provider="mock",
        model="video-v1",
        provider_request_id="provider-job-1",
    )
    runtime = ShotRuntime(
        compiled=compiled,
        status=ShotStatus.READY,
        clip=clip,
        actual_cost_usd=Decimal("0.4"),
    )
    job = VideoJob(
        job_id="77777777-7777-4777-8777-777777777777",
        spec=spec,
        status=VideoJobStatus.COMPOSING,
        shots=(runtime,),
    )
    rendered = RenderedVideo(
        object=DurableVideoObject(
            durable_ref="asset:video:final",
            bucket="generated-video",
            storage_key="video/final.mp4",
            size_bytes=4096,
        ),
        checksum_sha256="c" * 64,
        probe=probe,
        renderer_version="ffmpeg-7.1",
    )
    return job, runtime, clip, rendered, source


def test_clip_and_final_artifacts_use_video_contract_and_lineage():
    async def scenario():
        job, runtime, clip, rendered, source = _fixture()
        fake = FakeArtifactService()
        adapter = Node42VideoArtifactAdapter(
            cast(ArtifactEngineService, fake)
        )
        clip_version = await adapter.append_clip(job=job, clip=clip)
        clip_command = fake.commands[-1]
        assert clip_command.artifact_type is ArtifactType.VIDEO
        assert clip_command.initial_version is not None
        assert clip_command.initial_version.provenance.record.provider == "mock"
        assert clip_command.initial_version.provenance.record.model == "video-v1"
        assert clip_command.initial_version.provenance.record.input_asset_ids == (
            UUID(source.asset_id),
        )

        source_provenance = ShotProvenance(
            shot_id="hero",
            operation_id=runtime.compiled.paid_operation_id,
            retry_ordinal=0,
            provider="mock",
            model="video-v1",
            provider_request_id="provider-job-1",
            source_asset_ids=(source.asset_id,),
            identity_refs=(),
            rights_snapshot_ids=(source.rights_snapshot_id,),
            cost_usd=Decimal("0.4"),
            artifact_version_id=clip_version,
        )
        provenance = FinalVideoProvenance(
            task_semantic_hash=job.spec.semantic_hash(),
            source_shots=(source_provenance,),
            renderer_version="ffmpeg-7.1",
            brand_rule_snapshot_id=None,
            agent_run_id=None,
            agent_id=None,
            recipe_id=job.spec.recipe_id,
            skill_refs=job.spec.skill_refs,
            git_commit=job.spec.git_commit,
        )
        final_job = replace(
            job,
            shots=(replace(runtime, artifact_version_id=clip_version),),
            provenance=provenance,
        )
        await adapter.append_final(job=final_job, video=rendered)
        final_command = fake.commands[-1]
        assert final_command.artifact_type is ArtifactType.VIDEO
        assert final_command.initial_version is not None
        assert final_command.initial_version.lineage_sources == (
            (UUID(clip_version), LineageEdgeType.COMPOSED_FROM),
        )

    asyncio.run(scenario())
