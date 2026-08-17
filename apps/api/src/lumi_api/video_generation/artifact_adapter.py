from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from lumi_api.artifact_engine.contracts import (
    ArtifactCreateCommand,
    InitialVersionCreateCommand,
    ProvenanceEnvelope,
)
from lumi_api.artifact_engine.service import ArtifactEngineService
from lumi_api.artifacts.models import (
    ArtifactFile,
    ArtifactType,
    CreatedByType,
    FileRole,
    LineageEdgeType,
    ProvenanceRecord,
    RightsPolicy,
    RightsReviewStatus,
    SkillVersionRef,
)
from lumi_api.domain.ids import new_uuid7
from lumi_video_generation import RenderedVideo, StoredVideoClip, VideoJob


def _prompt_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _skills(job: VideoJob) -> tuple[SkillVersionRef, ...]:
    refs: list[SkillVersionRef] = []
    for raw in sorted(set(job.spec.skill_refs)):
        if "@" in raw:
            skill_id, version = raw.rsplit("@", 1)
        else:
            skill_id, version = raw, "unspecified"
        refs.append(SkillVersionRef(skill_id=skill_id, version=version))
    return tuple(refs)


def _creator(job: VideoJob) -> tuple[CreatedByType, str | None]:
    if job.spec.agent_run_id:
        return CreatedByType.AGENT, job.spec.agent_run_id
    return CreatedByType.SYSTEM, None


def _rights(job: VideoJob, source_reference: str) -> RightsPolicy:
    declaration = job.spec.user_use_declaration or "not supplied"
    return RightsPolicy(
        source_type="AI_GENERATED_VIDEO",
        owner_assertion=(
            f"generated/composed video; user use declaration: {declaration}"
        )[:240],
        license_type="PROVIDER_GENERATED_TERMS",
        commercial_use=None,
        redistribution=None,
        training_use=False,
        attribution_required=False,
        source_reference=source_reference,
        review_status=RightsReviewStatus.UNREVIEWED,
    )


def _git_sha(job: VideoJob) -> str:
    if job.spec.git_commit is None:
        raise ValueError("VIDEO_ARTIFACT_GIT_SHA_REQUIRED")
    return job.spec.git_commit


def _file(
    *,
    checksum_sha256: str,
    bucket: str,
    storage_key: str,
    size_bytes: int,
    mime_type: str,
    width: int,
    height: int,
    duration_seconds: Decimal,
    metadata: tuple[tuple[str, str], ...],
) -> ArtifactFile:
    return ArtifactFile(
        id=new_uuid7(),
        role=FileRole.ORIGINAL,
        bucket=bucket,
        storage_key=storage_key,
        mime_type=mime_type,
        size_bytes=size_bytes,
        checksum_sha256=checksum_sha256,
        width=width,
        height=height,
        duration_ms=int(duration_seconds * 1000),
        metadata=metadata,
    )


class Node42VideoArtifactAdapter:
    """Creates immutable clip/final VIDEO artifacts; never auto-approves them."""

    def __init__(self, service: ArtifactEngineService) -> None:
        self.service = service

    async def append_clip(
        self,
        *,
        job: VideoJob,
        clip: StoredVideoClip,
    ) -> str:
        runtime = next(
            item
            for item in job.shots
            if item.compiled.shot.shot_id == clip.shot_id
        )
        shot = runtime.compiled.shot
        now = datetime.now(UTC)
        created_by_type, created_by_id = _creator(job)
        rights = _rights(
            job,
            f"video-generation:{job.job_id}:shot:{shot.shot_id}",
        )
        input_assets = (
            ()
            if shot.source_ref is None
            else (UUID(shot.source_ref.asset_id),)
        )
        artifact_file = _file(
            checksum_sha256=clip.checksum_sha256,
            bucket=clip.object.bucket,
            storage_key=clip.object.storage_key,
            size_bytes=clip.object.size_bytes,
            mime_type=clip.probe.mime_type,
            width=clip.probe.width,
            height=clip.probe.height,
            duration_seconds=clip.probe.duration_seconds,
            metadata=(
                ("video_job_id", job.job_id),
                ("shot_id", shot.shot_id),
                ("retry_ordinal", str(runtime.compiled.retry_ordinal)),
                ("provider", clip.provider),
                ("model", clip.model),
                ("provider_request_id", clip.provider_request_id),
                (
                    "brand_rule_snapshot_id",
                    job.spec.brand_rule_snapshot_id or "none",
                ),
            ),
        )
        record = ProvenanceRecord(
            agent_run_id=(
                UUID(job.spec.agent_run_id)
                if job.spec.agent_run_id
                else None
            ),
            task_id=UUID(job.spec.task_id),
            generation_id=UUID(job.job_id),
            provider=clip.provider,
            model=clip.model,
            provider_request_id=clip.provider_request_id,
            prompt_hash=_prompt_hash(shot.prompt),
            prompt_ref=f"video-shot:{job.job_id}:{shot.shot_id}",
            input_asset_ids=input_assets,
            recipe_version=job.spec.recipe_id,
            skill_versions=_skills(job),
            code_git_sha=_git_sha(job),
        )
        artifact, branch = self.service.create_artifact(
            ArtifactCreateCommand(
                organization_id=UUID(job.spec.organization_id),
                project_id=UUID(job.spec.project_id),
                artifact_type=ArtifactType.VIDEO,
                name=f"Video shot {shot.shot_id}",
                rights=rights,
                created_by_type=created_by_type,
                created_by_id=created_by_id,
                created_at=now,
                initial_version=InitialVersionCreateCommand(
                    content_hash=clip.checksum_sha256,
                    files=(artifact_file,),
                    provenance=ProvenanceEnvelope(
                        record=record,
                        compiler_version="video-generation/1.0.0",
                        agent_version=job.spec.agent_id,
                    ),
                    rights=rights,
                    created_by_type=created_by_type,
                    created_by_id=created_by_id,
                    primary_file_id=artifact_file.id,
                ),
            )
        )
        if branch.head_version_id is None:
            raise RuntimeError("VIDEO_CLIP_ARTIFACT_VERSION_MISSING")
        ready = self.service.mark_ready(
            branch.head_version_id,
            occurred_at=now,
        )
        if ready.artifact_id != artifact.id:
            raise RuntimeError("VIDEO_CLIP_ARTIFACT_IDENTITY_MISMATCH")
        return str(ready.id)

    async def append_final(
        self,
        *,
        job: VideoJob,
        video: RenderedVideo,
    ) -> str:
        if job.provenance is None:
            raise ValueError("VIDEO_FINAL_PROVENANCE_REQUIRED")
        source_versions = tuple(
            UUID(item.artifact_version_id)
            for item in job.shots
            if item.artifact_version_id is not None
        )
        if len(source_versions) != len(job.shots):
            raise ValueError("VIDEO_FINAL_SHOT_ARTIFACTS_REQUIRED")
        now = datetime.now(UTC)
        created_by_type, created_by_id = _creator(job)
        rights = _rights(job, f"video-generation:{job.job_id}:final")
        artifact_file = _file(
            checksum_sha256=video.checksum_sha256,
            bucket=video.object.bucket,
            storage_key=video.object.storage_key,
            size_bytes=video.object.size_bytes,
            mime_type=video.probe.mime_type,
            width=video.probe.width,
            height=video.probe.height,
            duration_seconds=video.probe.duration_seconds,
            metadata=(
                ("video_job_id", job.job_id),
                ("renderer_version", video.renderer_version),
                ("task_semantic_hash", job.provenance.task_semantic_hash),
                (
                    "brand_rule_snapshot_id",
                    job.spec.brand_rule_snapshot_id or "none",
                ),
                ("shot_count", str(len(job.shots))),
            ),
        )
        input_assets = tuple(
            sorted(
                {
                    UUID(asset_id)
                    for source in job.provenance.source_shots
                    for asset_id in source.source_asset_ids
                },
                key=str,
            )
        )
        record = ProvenanceRecord(
            agent_run_id=(
                UUID(job.spec.agent_run_id)
                if job.spec.agent_run_id
                else None
            ),
            task_id=UUID(job.spec.task_id),
            prompt_hash=job.provenance.task_semantic_hash,
            prompt_ref=f"video-storyboard:{job.job_id}",
            input_asset_ids=input_assets,
            input_artifact_version_ids=source_versions,
            recipe_version=job.spec.recipe_id,
            skill_versions=_skills(job),
            code_git_sha=_git_sha(job),
        )
        artifact, branch = self.service.create_artifact(
            ArtifactCreateCommand(
                organization_id=UUID(job.spec.organization_id),
                project_id=UUID(job.spec.project_id),
                artifact_type=ArtifactType.VIDEO,
                name="Composed generated video",
                rights=rights,
                created_by_type=created_by_type,
                created_by_id=created_by_id,
                created_at=now,
                initial_version=InitialVersionCreateCommand(
                    content_hash=video.checksum_sha256,
                    files=(artifact_file,),
                    provenance=ProvenanceEnvelope(
                        record=record,
                        compiler_version="video-generation/1.0.0",
                        agent_version=job.spec.agent_id,
                    ),
                    rights=rights,
                    created_by_type=created_by_type,
                    created_by_id=created_by_id,
                    primary_file_id=artifact_file.id,
                    lineage_sources=tuple(
                        (version_id, LineageEdgeType.COMPOSED_FROM)
                        for version_id in source_versions
                    ),
                ),
            )
        )
        if branch.head_version_id is None:
            raise RuntimeError("VIDEO_FINAL_ARTIFACT_VERSION_MISSING")
        ready = self.service.mark_ready(
            branch.head_version_id,
            occurred_at=now,
        )
        if ready.artifact_id != artifact.id:
            raise RuntimeError("VIDEO_FINAL_ARTIFACT_IDENTITY_MISMATCH")
        return str(ready.id)
