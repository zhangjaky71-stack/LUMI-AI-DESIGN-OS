from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import uuid4

from lumi_image_generation import (
    CandidateStatus,
    ConstraintSeverity,
    GenerationCandidate,
    GenerationMode,
    GenerationProvenance,
    ImageGenerationSpec,
    OutputRequirements,
    QualityProfile,
    StoredImage,
    ValidationBundle,
    ValidationFinding,
    ValidationStatus,
)
from lumi_api.artifact_engine import (
    ArtifactEngineService,
    InMemoryArtifactRepository,
    StorageObjectMetadata,
)
from lumi_api.image_generation.artifact_adapter import Node42ArtifactCandidateAdapter


class FakeStorage:
    def __init__(self) -> None:
        self.objects = {}

    def add(self, organization_id, image: StoredImage) -> None:
        self.objects[(organization_id, image.bucket, image.storage_key)] = StorageObjectMetadata(
            organization_id=organization_id,
            bucket=image.bucket,
            storage_key=image.storage_key,
            checksum_sha256=image.checksum_sha256,
            size_bytes=image.size_bytes,
            mime_type=image.mime_type,
        )

    def stat_object(self, organization_id, bucket, storage_key):
        return self.objects.get((organization_id, bucket, storage_key))

    def list_objects(self, organization_id):
        return tuple(value for (org, _, _), value in self.objects.items() if org == organization_id)

    def delete_object(self, organization_id, bucket, storage_key):
        self.objects.pop((organization_id, bucket, storage_key), None)


def spec() -> ImageGenerationSpec:
    return ImageGenerationSpec(
        organization_id=uuid4(),
        project_id=uuid4(),
        task_id=uuid4(),
        operation_id=uuid4(),
        purpose="poster",
        mode=GenerationMode.TEXT_TO_IMAGE,
        prompt_compilation_ref="prompt:test",
        objective="poster",
        content="product",
        visual_direction="minimal",
        aspect_ratio="1:1",
        target_width=8,
        target_height=8,
        variant_count=1,
        references=(),
        identity_requirements=(),
        brand_rule_set_version=None,
        constraints=(),
        quality_profile=QualityProfile.BALANCED,
        budget_limit_usd=Decimal("1"),
        output_requirements=OutputRequirements(),
        code_git_sha="a" * 40,
        agent_run_id=uuid4(),
        agent_version="agent/1",
        recipe_version="recipe/1",
        skill_versions={"image-generation": "1"},
        user_use_declaration="commercial draft",
    )


def provenance(value: ImageGenerationSpec, candidate: GenerationCandidate) -> GenerationProvenance:
    return GenerationProvenance(
        generation_id=candidate.generation_id,
        organization_id=value.organization_id,
        project_id=value.project_id,
        task_id=value.task_id,
        operation_id=value.operation_id,
        variant_operation_id=candidate.variant_operation_id,
        variant_index=1,
        provider="mock",
        model="mock-image-v1",
        model_revision="rev1",
        registry_snapshot_id="registry1",
        provider_request_id="req1",
        prompt_hash="b" * 64,
        prompt_template_version="image-prompt-v1",
        prompt_compilation_ref=value.prompt_compilation_ref,
        reference_asset_ids=(),
        reference_asset_versions=(),
        seed=1,
        width=8,
        height=8,
        quality_profile=value.quality_profile,
        routing_reason_codes=("capability_match",),
        pricing_snapshot_id="price1",
        cost_usd=Decimal("0.01"),
        cost_confidence="exact",
        agent_run_id=value.agent_run_id,
        agent_version=value.agent_version,
        recipe_version=value.recipe_version,
        skill_versions=value.skill_versions,
        code_git_sha=value.code_git_sha,
        constraint_snapshot_hash="c" * 64,
        brand_rule_set_version=None,
        identity_validation_snapshot_id=None,
        brand_validation_snapshot_id=None,
        safety_metadata={},
        user_use_declaration=value.user_use_declaration,
    )


def test_node42_adapter_creates_unreviewed_raster_and_only_marks_passing_output_ready() -> None:
    value = spec()
    image = StoredImage("generated", "org/candidate.png", "image/png", 8, 8, 10, "d" * 64)
    storage = FakeStorage()
    storage.add(value.organization_id, image)
    repo = InMemoryArtifactRepository()
    adapter = Node42ArtifactCandidateAdapter(ArtifactEngineService(repo, storage))
    candidate = GenerationCandidate(
        uuid4(),
        uuid4(),
        1,
        uuid4(),
        CandidateStatus.VALIDATING,
        provider="mock",
        model="mock-image-v1",
    )
    validation = ValidationBundle(
        (
            ValidationFinding(
                "image-integrity",
                ValidationStatus.PASS,
                ConstraintSeverity.HARD,
                "PASS",
            ),
        )
    )
    result = asyncio.run(
        adapter.create_candidate(
            spec=value,
            candidate=candidate,
            stored=image,
            provenance=provenance(value, candidate),
            validation=validation,
        )
    )
    version = repo.get_version(result.artifact_version_id)
    assert result.status == "READY"
    assert version.status.value == "READY"
    assert version.rights.review_status.value == "UNREVIEWED"
    assert version.rights.commercial_use is None
    assert version.provenance.generation_id == candidate.generation_id

    rejected_candidate = GenerationCandidate(
        uuid4(), uuid4(), 1, uuid4(), CandidateStatus.VALIDATING
    )
    rejected_image = StoredImage(
        "generated", "org/rejected.png", "image/png", 8, 8, 10, "e" * 64
    )
    storage.add(value.organization_id, rejected_image)
    hard_fail = ValidationBundle(
        (
            ValidationFinding(
                "identity-engine",
                ValidationStatus.FAIL,
                ConstraintSeverity.HARD,
                "IDENTITY_FAIL",
            ),
        )
    )
    result = asyncio.run(
        adapter.create_candidate(
            spec=value,
            candidate=rejected_candidate,
            stored=rejected_image,
            provenance=provenance(value, rejected_candidate),
            validation=hard_fail,
        )
    )
    assert result.status == "DRAFT"
    assert repo.get_version(result.artifact_version_id).status.value == "DRAFT"
