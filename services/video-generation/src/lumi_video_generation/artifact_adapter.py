from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from lumi_artifacts.history import ArtifactHistory
from lumi_artifacts.model import Artifact, ArtifactBranch, ArtifactFile, ArtifactVersion, LineageEdge, ProvenanceRecord

from .model import CompiledShot, FinalVideoProvenance, RenderedVideo, ShotProvenance, ShotValidationReport, StoredVideoClip, VideoTaskSpec


def constraint_snapshot_hash(spec: VideoTaskSpec) -> str:
    payload = {
        "width": spec.width,
        "height": spec.height,
        "fps": spec.fps,
        "duration": format(spec.duration_seconds, "f"),
        "brand": spec.brand_rule_set_version,
        "identity": [(item.identity_id, item.reference_set_version, item.severity) for item in spec.identity_requirements],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _digest(*parts: str) -> str:
    return hashlib.sha256(":".join(parts).encode()).hexdigest()


class ArtifactHistoryVideoAdapter:
    """NODE-42 append-only adapter for generated shot attempts and final video."""

    def __init__(self, history: ArtifactHistory) -> None:
        self.history = history
        self.shot_provenance: dict[str, ShotProvenance] = {}
        self.final_provenance: dict[str, FinalVideoProvenance] = {}

    async def create_clip(
        self,
        *,
        spec: VideoTaskSpec,
        shot: CompiledShot,
        clip: StoredVideoClip,
        provenance: ShotProvenance,
        validation: ShotValidationReport,
        continuity_parent_version_ids: tuple[str, ...],
    ) -> str:
        digest = _digest(provenance.video_job_id, shot.shot.shot_id, provenance.paid_operation_id)
        artifact_id = f"artifact:video-clip:{digest}"
        branch_id = f"artifact-branch:video-clip:{digest}"
        version_id = f"artifact-version:video-clip:{digest}"
        file_id = f"artifact-file:video-clip:{digest}"
        if version_id in self.history.versions:
            return version_id
        self.history.add_artifact(Artifact(
            id=artifact_id,
            organization_id=spec.organization_id,
            project_id=spec.project_id,
            type="VIDEO",
            title=f"Video shot {shot.shot.shot_id} attempt",
        ))
        self.history.add_branch(ArtifactBranch(
            id=branch_id,
            organization_id=spec.organization_id,
            artifact_id=artifact_id,
            name="main",
            base_version_id=None,
            head_version_id=None,
            created_by=spec.agent_run_id or spec.task_id,
        ))
        version = ArtifactVersion(
            id=version_id,
            organization_id=spec.organization_id,
            artifact_id=artifact_id,
            branch_id=branch_id,
            parent_version_id=None,
            schema_version="video-clip.v1",
            version_number=1,
            status="DRAFT",
            content_hash=clip.checksum_sha256,
            constraint_snapshot_hash=constraint_snapshot_hash(spec),
            created_by_type="AGENT",
            created_by_id=spec.agent_run_id or spec.task_id,
            created_at=datetime.now(timezone.utc),
            primary_file_id=file_id,
            brand_rule_set_version=spec.brand_rule_set_version,
            identity_validation_snapshot_id=validation.identity_validation_snapshot_id,
        )
        self.history.add_version(version)
        self.history.add_file(ArtifactFile(
            id=file_id,
            organization_id=spec.organization_id,
            artifact_version_id=version_id,
            role="ORIGINAL",
            storage_key=clip.storage_key,
            mime_type=clip.mime_type,
            size_bytes=clip.size_bytes,
            checksum_sha256=clip.checksum_sha256,
            width=clip.width,
            height=clip.height,
            duration_ms=clip.duration_ms,
            metadata={
                "poster_frame_ref": clip.poster_frame_ref,
                "tail_frame_ref": clip.tail_frame_ref,
                "video_shot_provenance_snapshot_id": provenance.snapshot_id,
                "paid_operation_id": provenance.paid_operation_id,
            },
        ))
        source_asset_ids = [item.asset_id for item in spec.source_images]
        if shot.shot.source_ref is not None:
            source_asset_ids.append(shot.shot.source_ref.asset_id)
        input_versions = [item.artifact_version_id for item in spec.source_images if item.artifact_version_id]
        input_versions.extend(continuity_parent_version_ids)
        self.history.add_provenance(ProvenanceRecord(
            artifact_version_id=version_id,
            organization_id=spec.organization_id,
            constraint_snapshot_hash=constraint_snapshot_hash(spec),
            code_git_sha=spec.code_git_sha,
            brand_rule_set_version=spec.brand_rule_set_version,
            identity_validation_snapshot_id=validation.identity_validation_snapshot_id,
            agent_run_id=spec.agent_run_id,
            task_id=spec.task_id,
            generation_id=provenance.video_job_id,
            provider=provenance.provider,
            model=provenance.model,
            provider_request_id=provenance.provider_request_id,
            prompt_hash=provenance.prompt_hash,
            input_asset_ids=tuple(dict.fromkeys(source_asset_ids)),
            input_artifact_version_ids=tuple(dict.fromkeys(input_versions)),
            recipe_version=spec.recipe_version,
        ))
        parents = list(continuity_parent_version_ids)
        if shot.shot.source_ref and shot.shot.source_ref.artifact_version_id:
            parents.append(shot.shot.source_ref.artifact_version_id)
        for index, parent_id in enumerate(dict.fromkeys(parents)):
            if parent_id in self.history.versions:
                self.history.add_edge(LineageEdge(
                    id=f"artifact-edge:video-clip:{digest}:{index}",
                    organization_id=spec.organization_id,
                    from_version_id=parent_id,
                    to_version_id=version_id,
                    type="REFERENCE_USED",
                    metadata={"shot_id": shot.shot.shot_id, "paid_operation_id": provenance.paid_operation_id},
                ))
        if validation.decision == "PASS":
            self.history.transition_status(version_id, "READY")
        elif validation.decision == "REJECT":
            self.history.transition_status(version_id, "REJECTED")
        self.shot_provenance[provenance.snapshot_id] = provenance
        self.history.validate_integrity()
        return version_id

    async def create_final(
        self,
        *,
        spec: VideoTaskSpec,
        rendered: RenderedVideo,
        provenance: FinalVideoProvenance,
        validation: ShotValidationReport,
        clip_artifact_version_ids: tuple[str, ...],
    ) -> str:
        digest = _digest(provenance.video_job_id, "final")
        artifact_id = f"artifact:video-final:{digest}"
        branch_id = f"artifact-branch:video-final:{digest}"
        version_id = f"artifact-version:video-final:{digest}"
        file_id = f"artifact-file:video-final:{digest}"
        if version_id in self.history.versions:
            return version_id
        self.history.add_artifact(Artifact(
            id=artifact_id,
            organization_id=spec.organization_id,
            project_id=spec.project_id,
            type="VIDEO",
            title="Final generated video",
        ))
        self.history.add_branch(ArtifactBranch(
            id=branch_id,
            organization_id=spec.organization_id,
            artifact_id=artifact_id,
            name="main",
            base_version_id=None,
            head_version_id=None,
            created_by=spec.agent_run_id or spec.task_id,
        ))
        self.history.add_version(ArtifactVersion(
            id=version_id,
            organization_id=spec.organization_id,
            artifact_id=artifact_id,
            branch_id=branch_id,
            parent_version_id=None,
            schema_version="video-final.v1",
            version_number=1,
            status="DRAFT",
            content_hash=rendered.video.checksum_sha256,
            constraint_snapshot_hash=constraint_snapshot_hash(spec),
            created_by_type="AGENT",
            created_by_id=spec.agent_run_id or spec.task_id,
            created_at=datetime.now(timezone.utc),
            primary_file_id=file_id,
            brand_rule_set_version=spec.brand_rule_set_version,
        ))
        self.history.add_file(ArtifactFile(
            id=file_id,
            organization_id=spec.organization_id,
            artifact_version_id=version_id,
            role="ORIGINAL",
            storage_key=rendered.video.storage_key,
            mime_type=rendered.video.mime_type,
            size_bytes=rendered.video.size_bytes,
            checksum_sha256=rendered.video.checksum_sha256,
            width=rendered.video.width,
            height=rendered.video.height,
            duration_ms=rendered.video.duration_ms,
            metadata={"video_final_provenance_snapshot_id": provenance.snapshot_id},
        ))
        if rendered.thumbnail_storage_key and rendered.thumbnail_checksum_sha256:
            self.history.add_file(ArtifactFile(
                id=f"artifact-file:video-final-thumb:{digest}",
                organization_id=spec.organization_id,
                artifact_version_id=version_id,
                role="THUMBNAIL",
                storage_key=rendered.thumbnail_storage_key,
                mime_type="image/jpeg",
                size_bytes=0,
                checksum_sha256=rendered.thumbnail_checksum_sha256,
            ))
        if rendered.subtitle_storage_key and rendered.subtitle_checksum_sha256:
            self.history.add_file(ArtifactFile(
                id=f"artifact-file:video-final-subtitle:{digest}",
                organization_id=spec.organization_id,
                artifact_version_id=version_id,
                role="LAYER_DATA",
                storage_key=rendered.subtitle_storage_key,
                mime_type="text/vtt",
                size_bytes=0,
                checksum_sha256=rendered.subtitle_checksum_sha256,
            ))
        self.history.add_provenance(ProvenanceRecord(
            artifact_version_id=version_id,
            organization_id=spec.organization_id,
            constraint_snapshot_hash=constraint_snapshot_hash(spec),
            code_git_sha=spec.code_git_sha,
            brand_rule_set_version=spec.brand_rule_set_version,
            agent_run_id=spec.agent_run_id,
            task_id=spec.task_id,
            generation_id=provenance.video_job_id,
            prompt_hash=provenance.storyboard_hash,
            input_artifact_version_ids=clip_artifact_version_ids,
            recipe_version=spec.recipe_version,
        ))
        for index, clip_version_id in enumerate(clip_artifact_version_ids):
            self.history.add_edge(LineageEdge(
                id=f"artifact-edge:video-final:{digest}:{index}",
                organization_id=spec.organization_id,
                from_version_id=clip_version_id,
                to_version_id=version_id,
                type="COMPOSED_FROM",
                metadata={"ordinal": index + 1},
            ))
        if validation.decision == "PASS":
            self.history.transition_status(version_id, "READY")
        else:
            self.history.transition_status(version_id, "REJECTED")
        self.final_provenance[provenance.snapshot_id] = provenance
        self.history.validate_integrity()
        return version_id
