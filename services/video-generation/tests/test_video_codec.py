from __future__ import annotations

from decimal import Decimal

from lumi_api.video_generation.codec import decode_job, encode_job
from lumi_video_generation.model import (
    CompiledShot,
    DurableVideoObject,
    FinalVideoProvenance,
    RenderedVideo,
    ShotProvenance,
    ShotRuntime,
    ShotSpec,
    ShotStatus,
    ShotValidationReport,
    SourceImageRef,
    StoredVideoClip,
    ValidationDecision,
    VideoJob,
    VideoJobStatus,
    VideoMode,
    VideoProbeResult,
    VideoTaskSpec,
)


def test_completed_video_job_codec_round_trip():
    source = SourceImageRef(
        asset_id="11111111-1111-4111-8111-111111111111",
        asset_version="v1",
        durable_ref="asset:source:v1",
        checksum_sha256="a" * 64,
        rights_snapshot_id="rights-v1",
    )
    shot = ShotSpec(
        shot_id="hero",
        duration_seconds=Decimal("4.5"),
        prompt="Slow product orbit",
        source_ref=source,
        camera_motion="orbit-left",
        identity_refs=("product-identity-v1",),
        required_features=frozenset({"video.start_frame"}),
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
        budget_limit_usd=Decimal("1.25"),
        brand_rule_snapshot_id="brand-v1",
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
        duration_seconds=Decimal("4.5"),
        decodable_frames=135,
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
    artifact_version_id = "77777777-7777-4777-8777-777777777777"
    runtime = ShotRuntime(
        compiled=compiled,
        status=ShotStatus.READY,
        clip=clip,
        validation=ShotValidationReport(
            ValidationDecision.PASS,
            (),
            True,
            True,
        ),
        actual_cost_usd=Decimal("0.72"),
        artifact_version_id=artifact_version_id,
    )
    provenance = FinalVideoProvenance(
        task_semantic_hash=spec.semantic_hash(),
        source_shots=(
            ShotProvenance(
                shot_id="hero",
                operation_id=compiled.paid_operation_id,
                retry_ordinal=0,
                provider="mock",
                model="video-v1",
                provider_request_id="provider-job-1",
                source_asset_ids=(source.asset_id,),
                identity_refs=shot.identity_refs,
                rights_snapshot_ids=(source.rights_snapshot_id,),
                cost_usd=Decimal("0.72"),
                artifact_version_id=artifact_version_id,
            ),
        ),
        renderer_version="ffmpeg-7.1",
        brand_rule_snapshot_id="brand-v1",
        agent_run_id=None,
        agent_id=None,
        recipe_id="campaign-video-v1",
        skill_refs=("storyboard@1",),
        git_commit="d" * 40,
    )
    final = RenderedVideo(
        object=DurableVideoObject(
            durable_ref="asset:video:final",
            bucket="generated-video",
            storage_key="video/final.mp4",
            size_bytes=2048,
        ),
        checksum_sha256="c" * 64,
        probe=probe,
        renderer_version="ffmpeg-7.1",
    )
    job = VideoJob(
        job_id="88888888-8888-4888-8888-888888888888",
        spec=spec,
        status=VideoJobStatus.COMPLETED,
        shots=(runtime,),
        final_video=final,
        provenance=provenance,
        final_artifact_version_id=(
            "99999999-9999-4999-8999-999999999999"
        ),
    )

    encoded = encode_job(job)
    decoded = decode_job(encoded)

    assert decoded == job
    assert decoded.spec.semantic_hash() == spec.semantic_hash()
