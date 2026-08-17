from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from lumi_image_edit import (
    EditConstraint,
    EditIntent,
    ImageEditSpec,
    MaskSpec,
    PixelRect,
    ProtectedRegion,
    SourceImageRef,
)

MaskSourceValue = Literal["USER_BRUSH", "DESIGN_IR", "DETECTOR", "AGENT_PROPOSED"]
RegionRoleValue = Literal["EDITABLE", "PRODUCT", "LOGO", "QR", "LOCKED_TEXT", "CONTENT"]
SeverityValue = Literal["HARD", "SOFT", "ADVISORY"]


class Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PixelRectBody(Schema):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class SourceImageBody(Schema):
    artifact_id: UUID
    artifact_version_id: UUID
    asset_id: UUID
    asset_version: str = Field(min_length=1, max_length=160)
    durable_ref: str = Field(min_length=1, max_length=2000)
    checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    width: int = Field(gt=0, le=16384)
    height: int = Field(gt=0, le=16384)
    mime_type: str = Field(min_length=1, max_length=255)
    rights_assertion: str = Field(min_length=1, max_length=120)
    commercial_use_allowed: bool | None = None


class MaskBody(Schema):
    mask_id: UUID
    version: str = Field(min_length=1, max_length=160)
    source: MaskSourceValue
    source_asset_id: UUID
    source_asset_version: str = Field(min_length=1, max_length=160)
    source_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_width: int = Field(gt=0, le=16384)
    source_height: int = Field(gt=0, le=16384)
    editable_rect: PixelRectBody
    checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    durable_ref: str = Field(min_length=1, max_length=2000)
    preview_required: bool = False


class ProtectedRegionBody(Schema):
    region_id: str = Field(min_length=1, max_length=160)
    role: RegionRoleValue
    rect: PixelRectBody
    severity: SeverityValue
    source_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    identity_id: UUID | None = None
    expected_text: str | None = Field(default=None, max_length=4000)
    expected_qr_payload: str | None = Field(default=None, max_length=4000)


class ConstraintBody(Schema):
    constraint_id: str = Field(min_length=1, max_length=160)
    constraint_type: str = Field(min_length=1, max_length=160)
    severity: SeverityValue
    snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    parameters: dict[str, Any] = Field(default_factory=dict)


class IntentBody(Schema):
    action: str = Field(min_length=1, max_length=160)
    instruction: str = Field(min_length=1, max_length=16000)
    selected_node_ids: tuple[str, ...] = Field(default=(), max_length=128)
    value: Any | None = None
    allow_broad_change: bool = False


class SubmitImageEditRequest(Schema):
    task_id: UUID
    operation_id: UUID
    source: SourceImageBody
    intent: IntentBody
    constraints: tuple[ConstraintBody, ...] = Field(default=(), max_length=128)
    protected_regions: tuple[ProtectedRegionBody, ...] = Field(
        default=(), max_length=128
    )
    mask: MaskBody | None = None
    brand_rule_set_version: str | None = Field(default=None, max_length=160)
    identity_requirement_ids: tuple[UUID, ...] = Field(default=(), max_length=32)
    budget_limit_usd: Decimal = Field(ge=0, decimal_places=8, max_digits=20)
    design_document_id: UUID | None = None
    design_document_version: int | None = Field(default=None, ge=0)
    selected_node_kind: str | None = Field(default=None, max_length=80)
    agent_run_id: UUID | None = None
    agent_version: str | None = Field(default=None, max_length=160)
    recipe_version: str | None = Field(default=None, max_length=160)
    skill_versions: dict[str, str] = Field(default_factory=dict)
    seed: int | None = Field(default=None, ge=0, le=2**63 - 1)

    def to_domain(
        self,
        *,
        organization_id: UUID,
        project_id: UUID,
        code_git_sha: str,
    ) -> ImageEditSpec:
        source_body = self.source
        source = SourceImageRef(
            str(organization_id),
            str(project_id),
            str(source_body.artifact_id),
            str(source_body.artifact_version_id),
            str(source_body.asset_id),
            source_body.asset_version,
            source_body.durable_ref,
            source_body.checksum_sha256,
            source_body.width,
            source_body.height,
            source_body.mime_type,
            source_body.rights_assertion,
            source_body.commercial_use_allowed,
        )
        mask = None
        if self.mask:
            mask_body = self.mask
            rect = mask_body.editable_rect
            mask = MaskSpec(
                str(mask_body.mask_id),
                mask_body.version,
                mask_body.source,
                str(mask_body.source_asset_id),
                mask_body.source_asset_version,
                mask_body.source_checksum_sha256,
                mask_body.source_width,
                mask_body.source_height,
                PixelRect(rect.x, rect.y, rect.width, rect.height),
                mask_body.checksum_sha256,
                mask_body.durable_ref,
                mask_body.preview_required,
                None,
            )
        protected = tuple(
            ProtectedRegion(
                item.region_id,
                item.role,
                PixelRect(
                    item.rect.x,
                    item.rect.y,
                    item.rect.width,
                    item.rect.height,
                ),
                item.severity,
                item.source_checksum_sha256,
                str(item.identity_id) if item.identity_id else None,
                item.expected_text,
                item.expected_qr_payload,
            )
            for item in self.protected_regions
        )
        constraints = tuple(
            EditConstraint(
                item.constraint_id,
                item.constraint_type,
                item.severity,
                item.snapshot_hash,
                item.parameters,
            )
            for item in self.constraints
        )
        intent = EditIntent(
            self.intent.action,
            self.intent.instruction,
            self.intent.selected_node_ids,
            self.intent.value,
            self.intent.allow_broad_change,
            False,
        )
        return ImageEditSpec(
            str(organization_id),
            str(project_id),
            str(self.task_id),
            str(self.operation_id),
            source,
            intent,
            constraints,
            protected,
            mask,
            self.brand_rule_set_version,
            tuple(str(item) for item in self.identity_requirement_ids),
            self.budget_limit_usd,
            code_git_sha,
            str(self.design_document_id) if self.design_document_id else None,
            self.design_document_version,
            self.selected_node_kind,
            str(self.agent_run_id) if self.agent_run_id else None,
            self.agent_version,
            self.recipe_version,
            self.skill_versions,
            self.seed,
        )


class ImageEditResponse(Schema):
    edit_id: str
    operation_id: str
    route: str
    status: str
    source_artifact_version_id: str
    plan_reason_codes: tuple[str, ...]
    result_artifact_version_id: str | None
    result_design_document_version_id: str | None
    result_asset_id: str | None
    provider: str | None
    model: str | None
    provider_request_id: str | None
    provenance_snapshot_id: str | None
    validation_decision: str | None
    error_code: str | None

    @classmethod
    def from_job(cls, job: Any) -> ImageEditResponse:
        return cls(**{key: getattr(job, key) for key in cls.model_fields})
