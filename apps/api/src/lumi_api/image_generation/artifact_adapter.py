from __future__ import annotations

from datetime import UTC, datetime

from lumi_image_generation import (
    ArtifactCandidateResult,
    GenerationCandidate,
    GenerationProvenance,
    ImageGenerationSpec,
    StoredImage,
    ValidationBundle,
)
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
    ProvenanceRecord,
    RightsPolicy,
    RightsReviewStatus,
    SkillVersionRef,
)
from lumi_api.domain.ids import new_uuid7


class Node42ArtifactCandidateAdapter:
    """Creates immutable NODE-42 raster candidates; never auto-approves generation output."""

    def __init__(self, service: ArtifactEngineService) -> None:
        self.service = service

    @staticmethod
    def _rights(spec: ImageGenerationSpec, provenance: GenerationProvenance) -> RightsPolicy:
        declaration = spec.user_use_declaration or "not supplied"
        return RightsPolicy(
            source_type="AI_GENERATED",
            owner_assertion=f"generated output; user use declaration: {declaration}"[:240],
            license_type="PROVIDER_GENERATED_TERMS",
            commercial_use=None,
            redistribution=None,
            training_use=False,
            attribution_required=False,
            source_reference=f"generation:{provenance.generation_id}",
            review_status=RightsReviewStatus.UNREVIEWED,
        )

    async def create_candidate(
        self,
        *,
        spec: ImageGenerationSpec,
        candidate: GenerationCandidate,
        stored: StoredImage,
        provenance: GenerationProvenance,
        validation: ValidationBundle,
    ) -> ArtifactCandidateResult:
        now = datetime.now(UTC)
        file_id = new_uuid7()
        rights = self._rights(spec, provenance)
        created_by_type = (
            CreatedByType.AGENT if spec.agent_run_id is not None else CreatedByType.SYSTEM
        )
        created_by_id = str(spec.agent_run_id) if spec.agent_run_id is not None else None
        record = ProvenanceRecord(
            agent_run_id=spec.agent_run_id,
            task_id=spec.task_id,
            generation_id=provenance.generation_id,
            provider=provenance.provider,
            model=provenance.model,
            provider_request_id=provenance.provider_request_id,
            prompt_hash=provenance.prompt_hash,
            prompt_ref=provenance.prompt_compilation_ref,
            prompt_template_version=provenance.prompt_template_version,
            input_asset_ids=provenance.reference_asset_ids,
            constraint_snapshot_hash=provenance.constraint_snapshot_hash,
            recipe_version=provenance.recipe_version,
            skill_versions=tuple(
                SkillVersionRef(skill_id=key, version=value)
                for key, value in sorted(provenance.skill_versions.items())
            ),
            code_git_sha=provenance.code_git_sha,
        )
        metadata = (
            ("generation_provenance_snapshot_id", provenance.snapshot_id),
            ("provider_model_revision", provenance.model_revision or "unknown"),
            ("provider_registry_snapshot", provenance.registry_snapshot_id or "unknown"),
            ("pricing_snapshot_id", provenance.pricing_snapshot_id or "unknown"),
            ("brand_validation_snapshot", provenance.brand_validation_snapshot_id or "none"),
            ("identity_validation_snapshot", provenance.identity_validation_snapshot_id or "none"),
        )
        file = ArtifactFile(
            id=file_id,
            role=FileRole.ORIGINAL,
            bucket=stored.bucket,
            storage_key=stored.storage_key,
            mime_type=stored.mime_type,
            size_bytes=stored.size_bytes,
            checksum_sha256=stored.checksum_sha256,
            width=stored.width,
            height=stored.height,
            metadata=metadata,
        )
        artifact, branch = self.service.create_artifact(
            ArtifactCreateCommand(
                organization_id=spec.organization_id,
                project_id=spec.project_id,
                artifact_type=ArtifactType.RASTER_IMAGE,
                name=f"Generated image variant {candidate.variant_index}",
                rights=rights,
                created_by_type=created_by_type,
                created_by_id=created_by_id,
                created_at=now,
                initial_version=InitialVersionCreateCommand(
                    content_hash=stored.checksum_sha256,
                    files=(file,),
                    provenance=ProvenanceEnvelope(
                        record=record,
                        compiler_version="image-generation/1.0.0",
                        agent_version=spec.agent_version,
                    ),
                    rights=rights,
                    created_by_type=created_by_type,
                    created_by_id=created_by_id,
                    primary_file_id=file_id,
                    constraint_snapshot_hash=provenance.constraint_snapshot_hash,
                ),
            )
        )
        version_id = branch.head_version_id
        if version_id is None:
            raise RuntimeError("GENERATION_ARTIFACT_INITIAL_VERSION_MISSING")
        status = "DRAFT"
        if not validation.hard_failed:
            ready = self.service.mark_ready(version_id, occurred_at=now)
            status = ready.status.value
        return ArtifactCandidateResult(
            artifact_id=artifact.id,
            artifact_version_id=version_id,
            status=status,
        )
