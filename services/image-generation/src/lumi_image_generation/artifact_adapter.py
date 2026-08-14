from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from lumi_artifacts.history import ArtifactHistory
from lumi_artifacts.model import (
    Artifact,
    ArtifactBranch,
    ArtifactFile,
    ArtifactVersion,
    ProvenanceRecord,
)

from .model import (
    GenerationCandidate,
    GenerationProvenanceSnapshot,
    ImageGenerationSpec,
    StoredImage,
    ValidationBundle,
)
from .ports import ArtifactCandidateResult


class ArtifactHistoryCandidateAdapter:
    """Executable NODE-42 integration adapter used by NODE-46 conformance/integration tests.

    Production persistence can replace this adapter with the DB-backed ArtifactService while
    preserving the same immutable Artifact/Version/File/Provenance semantics.
    """

    def __init__(self, history: ArtifactHistory) -> None:
        self.history = history

    async def create_candidate(
        self,
        *,
        spec: ImageGenerationSpec,
        candidate: GenerationCandidate,
        stored: StoredImage,
        provenance: GenerationProvenanceSnapshot,
        validation: ValidationBundle,
    ) -> ArtifactCandidateResult:
        artifact_id = f"artifact:{candidate.candidate_id}"
        branch_id = f"artifact-branch:{candidate.candidate_id}"
        version_id = f"artifact-version:{candidate.candidate_id}"
        file_id = f"artifact-file:{candidate.candidate_id}"

        existing = self.history.versions.get(version_id)
        if existing is not None:
            return ArtifactCandidateResult(
                artifact_id=artifact_id,
                artifact_version_id=version_id,
                status=existing.status,
            )

        self.history.add_artifact(
            Artifact(
                id=artifact_id,
                organization_id=spec.organization_id,
                project_id=spec.project_id,
                type="RASTER_IMAGE",
                title=f"Generated image variant {candidate.variant_index}",
            )
        )
        self.history.add_branch(
            ArtifactBranch(
                id=branch_id,
                organization_id=spec.organization_id,
                artifact_id=artifact_id,
                name="main",
                base_version_id=None,
                head_version_id=None,
                created_by=spec.agent_run_id or spec.task_id,
            )
        )
        version = ArtifactVersion(
            id=version_id,
            organization_id=spec.organization_id,
            artifact_id=artifact_id,
            branch_id=branch_id,
            parent_version_id=None,
            schema_version="raster-image-v1",
            version_number=1,
            status="DRAFT",
            content_hash=stored.checksum_sha256,
            constraint_snapshot_hash=spec.hard_constraint_snapshot_hash,
            created_by_type="AGENT",
            created_by_id=spec.agent_run_id or spec.task_id,
            created_at=datetime.now(timezone.utc),
            primary_file_id=file_id,
            brand_rule_set_version=spec.brand_rule_set_version,
            identity_validation_snapshot_id=validation.identity_validation_snapshot_id,
        )
        self.history.add_version(version)
        self.history.add_file(
            ArtifactFile(
                id=file_id,
                organization_id=spec.organization_id,
                artifact_version_id=version_id,
                role="ORIGINAL",
                storage_key=stored.storage_key,
                mime_type=stored.mime_type,
                size_bytes=stored.size_bytes,
                checksum_sha256=stored.checksum_sha256,
                width=stored.width,
                height=stored.height,
                metadata={
                    "generation_provenance_snapshot_id": provenance.snapshot_id,
                    "prompt_compilation_ref": provenance.prompt_compilation_ref,
                    "routing_reason_codes": provenance.routing_reason_codes,
                    "seed": provenance.seed,
                    "pricing_snapshot_id": provenance.pricing_snapshot_id,
                    "cost_usd": (
                        format(provenance.cost_usd, "f")
                        if isinstance(provenance.cost_usd, Decimal)
                        else None
                    ),
                    "cost_confidence": provenance.cost_confidence,
                    "safety_metadata": dict(provenance.safety_metadata),
                },
            )
        )
        self.history.add_provenance(
            ProvenanceRecord(
                artifact_version_id=version_id,
                organization_id=spec.organization_id,
                constraint_snapshot_hash=spec.hard_constraint_snapshot_hash,
                code_git_sha=spec.code_git_sha,
                brand_rule_set_version=spec.brand_rule_set_version,
                identity_validation_snapshot_id=validation.identity_validation_snapshot_id,
                agent_run_id=spec.agent_run_id,
                task_id=spec.task_id,
                generation_id=provenance.generation_id,
                provider=provenance.provider,
                model=provenance.model,
                provider_request_id=provenance.provider_request_id,
                prompt_hash=provenance.prompt_hash,
                prompt_template_version=provenance.prompt_template_version,
                input_asset_ids=tuple(reference.asset_id for reference in spec.references),
                recipe_version=spec.recipe_version,
                skill_versions=spec.skill_versions,
            )
        )

        target = "REJECTED" if validation.hard_failed else "READY"
        updated = self.history.transition_status(version_id, target)
        self.history.validate_integrity()
        return ArtifactCandidateResult(
            artifact_id=artifact_id,
            artifact_version_id=version_id,
            status=updated.status,
        )
