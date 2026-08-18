from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Mapping

from .contracts_common import (
    EditRoute,
    MaskSource,
    PixelRect,
    RegionRole,
    Severity,
    _canonical,
    canonical_hash,
)


@dataclass(frozen=True, slots=True)
class SourceImageRef:
    organization_id: str
    project_id: str
    artifact_id: str
    artifact_version_id: str
    asset_id: str
    asset_version: str
    durable_ref: str
    checksum_sha256: str
    width: int
    height: int
    mime_type: str
    rights_assertion: str
    commercial_use_allowed: bool | None

    def __post_init__(self) -> None:
        required = (
            self.organization_id,
            self.project_id,
            self.artifact_id,
            self.artifact_version_id,
            self.asset_id,
            self.asset_version,
            self.durable_ref,
            self.mime_type,
        )
        if any(not value.strip() for value in required):
            raise ValueError("IMAGE_EDIT_SOURCE_REQUIRED_FIELD_MISSING")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("IMAGE_EDIT_SOURCE_DIMENSIONS_INVALID")
        if len(self.checksum_sha256) != 64:
            raise ValueError("IMAGE_EDIT_SOURCE_CHECKSUM_INVALID")
        if "://" in self.durable_ref:
            raise ValueError("IMAGE_EDIT_SOURCE_DURABLE_REF_URL_FORBIDDEN")


@dataclass(frozen=True, slots=True)
class MaskSpec:
    mask_id: str
    version: str
    source: MaskSource
    source_asset_id: str
    source_asset_version: str
    source_checksum_sha256: str
    source_width: int
    source_height: int
    editable_rect: PixelRect
    checksum_sha256: str
    durable_ref: str
    preview_required: bool = False
    preview_approved_by: str | None = None

    def __post_init__(self) -> None:
        if not self.mask_id or not self.version:
            raise ValueError("IMAGE_EDIT_MASK_ID_VERSION_REQUIRED")
        if self.source_width <= 0 or self.source_height <= 0:
            raise ValueError("IMAGE_EDIT_MASK_SOURCE_DIMENSIONS_INVALID")
        if self.editable_rect.right > self.source_width or self.editable_rect.bottom > self.source_height:
            raise ValueError("IMAGE_EDIT_MASK_OUTSIDE_SOURCE")
        if len(self.source_checksum_sha256) != 64 or len(self.checksum_sha256) != 64:
            raise ValueError("IMAGE_EDIT_MASK_CHECKSUM_INVALID")
        if "://" in self.durable_ref:
            raise ValueError("IMAGE_EDIT_MASK_DURABLE_REF_URL_FORBIDDEN")


@dataclass(frozen=True, slots=True)
class ProtectedRegion:
    region_id: str
    role: RegionRole
    rect: PixelRect
    severity: Severity
    source_checksum_sha256: str
    identity_id: str | None = None
    expected_text: str | None = None
    expected_qr_payload: str | None = None

    def __post_init__(self) -> None:
        if not self.region_id:
            raise ValueError("IMAGE_EDIT_PROTECTED_REGION_ID_REQUIRED")
        if len(self.source_checksum_sha256) != 64:
            raise ValueError("IMAGE_EDIT_PROTECTED_HASH_INVALID")
        if self.role == "QR" and not self.expected_qr_payload:
            raise ValueError("IMAGE_EDIT_QR_PAYLOAD_REQUIRED")
        if self.role == "LOCKED_TEXT" and not self.expected_text:
            raise ValueError("IMAGE_EDIT_LOCKED_TEXT_REQUIRED")


@dataclass(frozen=True, slots=True)
class EditConstraint:
    constraint_id: str
    constraint_type: str
    severity: Severity
    snapshot_hash: str
    parameters: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.constraint_id or not self.constraint_type:
            raise ValueError("IMAGE_EDIT_CONSTRAINT_REQUIRED_FIELD_MISSING")
        if len(self.snapshot_hash) != 64:
            raise ValueError("IMAGE_EDIT_CONSTRAINT_HASH_INVALID")
        _canonical(self.parameters)


@dataclass(frozen=True, slots=True)
class StructuralEditOperation:
    operation_id: str
    type: str
    target_ids: tuple[str, ...]
    expected_document_version: int
    payload: Mapping[str, object]
    reason: str

    def __post_init__(self) -> None:
        if not self.operation_id or not self.type or not self.reason:
            raise ValueError("IMAGE_EDIT_STRUCTURAL_OPERATION_INCOMPLETE")
        if not self.target_ids or len(self.target_ids) != len(set(self.target_ids)):
            raise ValueError("IMAGE_EDIT_STRUCTURAL_TARGETS_INVALID")
        if self.expected_document_version < 0:
            raise ValueError("IMAGE_EDIT_DOCUMENT_VERSION_INVALID")
        _canonical(self.payload)


@dataclass(frozen=True, slots=True)
class EditIntent:
    action: str
    instruction: str
    selected_node_ids: tuple[str, ...] = ()
    value: object | None = None
    allow_broad_change: bool = False
    broad_change_confirmed: bool = False
    broad_change_confirmed_by: str | None = None

    def __post_init__(self) -> None:
        if not self.action.strip() or not self.instruction.strip():
            raise ValueError("IMAGE_EDIT_INTENT_REQUIRED")
        if len(self.selected_node_ids) != len(set(self.selected_node_ids)):
            raise ValueError("IMAGE_EDIT_SELECTED_NODE_DUPLICATE")
        _canonical(self.value)


@dataclass(frozen=True, slots=True)
class ImageEditSpec:
    organization_id: str
    project_id: str
    task_id: str
    operation_id: str
    source: SourceImageRef
    intent: EditIntent
    constraints: tuple[EditConstraint, ...]
    protected_regions: tuple[ProtectedRegion, ...]
    mask: MaskSpec | None
    brand_rule_set_version: str | None
    identity_requirement_ids: tuple[str, ...]
    budget_limit_usd: Decimal
    code_git_sha: str
    design_document_id: str | None = None
    design_document_version: int | None = None
    selected_node_kind: str | None = None
    agent_run_id: str | None = None
    agent_version: str | None = None
    recipe_version: str | None = None
    skill_versions: Mapping[str, str] = field(default_factory=dict)
    seed: int | None = None
    target_branch_id: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.budget_limit_usd, float) or not self.budget_limit_usd.is_finite() or self.budget_limit_usd < 0:
            raise ValueError("IMAGE_EDIT_BUDGET_INVALID")
        if len(self.code_git_sha) != 40:
            raise ValueError("IMAGE_EDIT_GIT_SHA_INVALID")
        if self.source.organization_id != self.organization_id or self.source.project_id != self.project_id:
            raise ValueError("IMAGE_EDIT_SOURCE_SCOPE_MISMATCH")
        if self.design_document_version is not None and self.design_document_version < 0:
            raise ValueError("IMAGE_EDIT_DESIGN_DOCUMENT_VERSION_INVALID")
        if len(self.identity_requirement_ids) != len(set(self.identity_requirement_ids)):
            raise ValueError("IMAGE_EDIT_IDENTITY_REQUIREMENT_DUPLICATE")
        region_ids = [region.region_id for region in self.protected_regions]
        if len(region_ids) != len(set(region_ids)):
            raise ValueError("IMAGE_EDIT_PROTECTED_REGION_DUPLICATE")
        for region in self.protected_regions:
            if region.source_checksum_sha256 != self.source.checksum_sha256:
                raise ValueError("IMAGE_EDIT_PROTECTED_SOURCE_HASH_MISMATCH")
            if region.rect.right > self.source.width or region.rect.bottom > self.source.height:
                raise ValueError("IMAGE_EDIT_PROTECTED_REGION_OUTSIDE_SOURCE")
        if self.mask:
            if (self.mask.source_asset_id, self.mask.source_asset_version) != (
                self.source.asset_id,
                self.source.asset_version,
            ):
                raise ValueError("IMAGE_EDIT_MASK_SOURCE_VERSION_MISMATCH")
            if self.mask.source_checksum_sha256 != self.source.checksum_sha256:
                raise ValueError("IMAGE_EDIT_MASK_SOURCE_CHECKSUM_MISMATCH")
            if (self.mask.source_width, self.mask.source_height) != (
                self.source.width,
                self.source.height,
            ):
                raise ValueError("IMAGE_EDIT_MASK_SOURCE_DIMENSION_MISMATCH")
        if self.target_branch_id is not None and not self.target_branch_id.strip():
            raise ValueError("IMAGE_EDIT_TARGET_BRANCH_INVALID")
        _canonical(self.skill_versions)

    @property
    def semantic_hash(self) -> str:
        value = asdict(self)
        value.pop("budget_limit_usd", None)
        value["intent"].pop("broad_change_confirmed", None)
        value["intent"].pop("broad_change_confirmed_by", None)
        if value.get("mask"):
            value["mask"].pop("preview_approved_by", None)
        return canonical_hash(value)


@dataclass(frozen=True, slots=True)
class EditPlan:
    route: EditRoute
    reason_codes: tuple[str, ...]
    structural_operations: tuple[StructuralEditOperation, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    requires_provider: bool = False
    requires_mask: bool = False
    requires_user_confirmation: bool = False
