from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from lumi_image_generation import (
    ConstraintSeverity,
    GenerationConstraint,
    GenerationMode,
    IdentityRequirement,
    ImageGenerationSpec,
    ImageReference,
    OutputFormat,
    OutputRequirements,
    QualityProfile,
    ReferenceRole,
    ReferenceSource,
)


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ImageReferenceBody(Schema):
    asset_id: UUID
    asset_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    role: ReferenceRole
    source: ReferenceSource
    note: str | None = Field(default=None, max_length=1000)


class IdentityRequirementBody(Schema):
    identity_id: UUID
    reference_set_version: str = Field(min_length=1, max_length=160)
    severity: ConstraintSeverity = ConstraintSeverity.HARD
    scenario: str = Field(min_length=1, max_length=160)


class GenerationConstraintBody(Schema):
    constraint_id: str = Field(min_length=1, max_length=160)
    constraint_type: str = Field(min_length=1, max_length=160)
    severity: ConstraintSeverity
    snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    parameters: dict[str, Any] = Field(default_factory=dict)


class OutputRequirementsBody(Schema):
    format: OutputFormat = OutputFormat.PNG
    transparent_background: bool = False
    exact_dimensions: bool = True
    minimum_width: int | None = Field(default=None, ge=1, le=16384)
    minimum_height: int | None = Field(default=None, ge=1, le=16384)


class SubmitImageGenerationRequest(Schema):
    task_id: UUID
    operation_id: UUID
    purpose: str = Field(min_length=1, max_length=500)
    mode: GenerationMode
    prompt_compilation_ref: str = Field(min_length=1, max_length=500)
    objective: str = Field(min_length=1, max_length=8000)
    content: str = Field(min_length=1, max_length=16000)
    visual_direction: str = Field(default="", max_length=8000)
    aspect_ratio: str = Field(min_length=1, max_length=40)
    target_width: int = Field(ge=1, le=16384)
    target_height: int = Field(ge=1, le=16384)
    variant_count: int = Field(default=1, ge=1, le=16)
    references: tuple[ImageReferenceBody, ...] = Field(default=(), max_length=32)
    identity_requirements: tuple[IdentityRequirementBody, ...] = Field(
        default=(), max_length=16
    )
    brand_rule_set_version: str | None = Field(default=None, max_length=160)
    constraints: tuple[GenerationConstraintBody, ...] = Field(default=(), max_length=128)
    quality_profile: QualityProfile = QualityProfile.BALANCED
    budget_limit_usd: Decimal = Field(ge=0, decimal_places=8, max_digits=20)
    output_requirements: OutputRequirementsBody = Field(default_factory=OutputRequirementsBody)
    agent_run_id: UUID | None = None
    agent_version: str | None = Field(default=None, max_length=160)
    recipe_version: str | None = Field(default=None, max_length=160)
    skill_versions: dict[str, str] = Field(default_factory=dict)
    seed: int | None = Field(default=None, ge=0, le=2**63 - 1)
    user_intent_ref: str | None = Field(default=None, max_length=500)
    user_use_declaration: str | None = Field(default=None, max_length=2000)

    def to_domain(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        code_git_sha: str,
    ) -> ImageGenerationSpec:
        return ImageGenerationSpec(
            organization_id=organization_id,
            project_id=project_id,
            task_id=self.task_id,
            operation_id=self.operation_id,
            purpose=self.purpose,
            mode=self.mode,
            prompt_compilation_ref=self.prompt_compilation_ref,
            objective=self.objective,
            content=self.content,
            visual_direction=self.visual_direction,
            aspect_ratio=self.aspect_ratio,
            target_width=self.target_width,
            target_height=self.target_height,
            variant_count=self.variant_count,
            references=tuple(
                ImageReference(
                    item.asset_id,
                    item.asset_version,
                    item.role,
                    item.source,
                    item.note,
                )
                for item in self.references
            ),
            identity_requirements=tuple(
                IdentityRequirement(
                    item.identity_id,
                    item.reference_set_version,
                    item.severity,
                    item.scenario,
                )
                for item in self.identity_requirements
            ),
            brand_rule_set_version=self.brand_rule_set_version,
            constraints=tuple(
                GenerationConstraint(
                    item.constraint_id,
                    item.constraint_type,
                    item.severity,
                    item.snapshot_hash,
                    item.parameters,
                )
                for item in self.constraints
            ),
            quality_profile=self.quality_profile,
            budget_limit_usd=self.budget_limit_usd,
            output_requirements=OutputRequirements(
                self.output_requirements.format,
                self.output_requirements.transparent_background,
                self.output_requirements.exact_dimensions,
                self.output_requirements.minimum_width,
                self.output_requirements.minimum_height,
            ),
            code_git_sha=code_git_sha,
            agent_run_id=self.agent_run_id,
            agent_version=self.agent_version,
            recipe_version=self.recipe_version,
            skill_versions=self.skill_versions,
            seed=self.seed,
            user_intent_ref=self.user_intent_ref,
            user_use_declaration=self.user_use_declaration,
        )


class CandidateResponse(Schema):
    candidate_id: UUID
    variant_index: int
    status: str
    provider: str | None
    model: str | None
    provider_request_id: str | None
    artifact_id: UUID | None
    artifact_version_id: UUID | None
    cost_usd: Decimal | None
    cost_confidence: str | None
    pricing_snapshot_id: str | None
    error_code: str | None


class ImageGenerationResponse(Schema):
    generation_id: UUID
    project_id: UUID
    task_id: UUID
    operation_id: UUID
    status: str
    prompt_hash: str
    requested_variants: int
    selected_variants: int
    estimated_total_usd: Decimal
    variant_reason_codes: tuple[str, ...]
    candidates: tuple[CandidateResponse, ...]
    created_at: str
    updated_at: str
    completed_at: str | None
    error_code: str | None

    @classmethod
    def from_job(cls, job) -> "ImageGenerationResponse":
        return cls(
            generation_id=job.generation_id,
            project_id=job.project_id,
            task_id=job.task_id,
            operation_id=job.operation_id,
            status=job.status.value,
            prompt_hash=job.prompt_hash,
            requested_variants=job.variant_decision.requested_count,
            selected_variants=job.variant_decision.selected_count,
            estimated_total_usd=job.variant_decision.estimated_total_usd,
            variant_reason_codes=job.variant_decision.reason_codes,
            candidates=tuple(
                CandidateResponse(
                    candidate_id=item.candidate_id,
                    variant_index=item.variant_index,
                    status=item.status.value,
                    provider=item.provider,
                    model=item.model,
                    provider_request_id=item.provider_request_id,
                    artifact_id=item.artifact_id,
                    artifact_version_id=item.artifact_version_id,
                    cost_usd=item.cost_usd,
                    cost_confidence=item.cost_confidence,
                    pricing_snapshot_id=item.pricing_snapshot_id,
                    error_code=item.error_code,
                )
                for item in job.candidates
            ),
            created_at=job.created_at,
            updated_at=job.updated_at,
            completed_at=job.completed_at,
            error_code=job.error_code,
        )
