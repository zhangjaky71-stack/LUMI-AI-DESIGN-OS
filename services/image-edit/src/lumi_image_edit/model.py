from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal, Mapping

EditRoute = Literal[
    "STRUCTURAL_IR_EDIT",
    "PIXEL_LOCAL_EDIT",
    "REGENERATE_REGION",
    "FULL_IMAGE_EDIT",
    "HYBRID",
]
EditStatus = Literal[
    "PLANNED",
    "RUNNING",
    "PROVIDER_PENDING",
    "VALIDATING",
    "COMPLETED",
    "REPAIR_REQUIRED",
    "REJECTED",
    "FAILED",
]
MaskSource = Literal["USER_BRUSH", "DESIGN_IR", "DETECTOR", "AGENT_PROPOSED"]
RegionRole = Literal["EDITABLE", "PRODUCT", "LOGO", "QR", "LOCKED_TEXT", "CONTENT"]
Severity = Literal["HARD", "SOFT", "ADVISORY"]
StructuralOperationType = Literal[
    "SET_PROPERTY",
    "MOVE_NODE",
    "RESIZE_NODE",
    "REORDER_NODE",
    "REPARENT_NODE",
    "REPLACE_ASSET",
    "SET_TEXT",
    "APPLY_STYLE",
]


def _sha(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _require_text(value: str, code: str) -> None:
    if not value or not value.strip():
        raise ValueError(code)


@dataclass(frozen=True, slots=True)
class PixelRect:
    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.x < 0 or self.y < 0 or self.width <= 0 or self.height <= 0:
            raise ValueError("IMAGE_EDIT_PIXEL_RECT_INVALID")

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height


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
    rights: str
    commercial_use_allowed: bool

    def __post_init__(self) -> None:
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
        if self.editable_rect.right > self.source_width or self.editable_rect.bottom > self.source_height:
            raise ValueError("IMAGE_EDIT_MASK_OUTSIDE_SOURCE")
        if len(self.source_checksum_sha256) != 64 or len(self.checksum_sha256) != 64:
            raise ValueError("IMAGE_EDIT_MASK_CHECKSUM_INVALID")
        if self.preview_required and not self.preview_approved_by:
            raise ValueError("IMAGE_EDIT_HIGH_IMPACT_MASK_REQUIRES_APPROVAL")


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
        if len(self.snapshot_hash) != 64:
            raise ValueError("IMAGE_EDIT_CONSTRAINT_HASH_INVALID")


@dataclass(frozen=True, slots=True)
class StructuralEditOperation:
    operation_id: str
    type: StructuralOperationType
    target_ids: tuple[str, ...]
    expected_document_version: int
    payload: Mapping[str, object]
    reason: str

    def __post_init__(self) -> None:
        if self.expected_document_version < 0 or not self.target_ids:
            raise ValueError("IMAGE_EDIT_STRUCTURAL_OPERATION_INVALID")


@dataclass(frozen=True, slots=True)
class EditIntent:
    action: str
    instruction: str
    selected_node_ids: tuple[str, ...] = ()
    value: object | None = None
    allow_broad_change: bool = False

    def __post_init__(self) -> None:
        _require_text(self.action, "IMAGE_EDIT_ACTION_REQUIRED")
        _require_text(self.instruction, "IMAGE_EDIT_INSTRUCTION_REQUIRED")


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
    recipe_version: str | None = None
    seed: int | None = None

    def __post_init__(self) -> None:
        if isinstance(self.budget_limit_usd, float):
            raise ValueError("IMAGE_EDIT_BUDGET_FLOAT_FORBIDDEN")
        if self.budget_limit_usd < 0:
            raise ValueError("IMAGE_EDIT_BUDGET_INVALID")
        if len(self.code_git_sha) != 40:
            raise ValueError("IMAGE_EDIT_GIT_SHA_INVALID")
        if self.mask is not None:
            if self.mask.source_asset_id != self.source.asset_id or self.mask.source_asset_version != self.source.asset_version:
                raise ValueError("IMAGE_EDIT_MASK_SOURCE_VERSION_MISMATCH")
            if self.mask.source_checksum_sha256 != self.source.checksum_sha256:
                raise ValueError("IMAGE_EDIT_MASK_SOURCE_CHECKSUM_MISMATCH")
            if (self.mask.source_width, self.mask.source_height) != (self.source.width, self.source.height):
                raise ValueError("IMAGE_EDIT_MASK_SOURCE_DIMENSION_MISMATCH")

    @property
    def semantic_hash(self) -> str:
        return _sha({
            "organization_id": self.organization_id,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "source": self.source,
            "intent": self.intent,
            "constraints": self.constraints,
            "protected_regions": self.protected_regions,
            "mask": self.mask,
            "brand_rule_set_version": self.brand_rule_set_version,
            "identity_requirement_ids": self.identity_requirement_ids,
            "design_document_id": self.design_document_id,
            "design_document_version": self.design_document_version,
            "selected_node_kind": self.selected_node_kind,
            "seed": self.seed,
        })


@dataclass(frozen=True, slots=True)
class EditPlan:
    route: EditRoute
    reason_codes: tuple[str, ...]
    structural_operations: tuple[StructuralEditOperation, ...] = ()
    requires_provider: bool = False
    requires_mask: bool = False
    requires_user_confirmation: bool = False


@dataclass(frozen=True, slots=True)
class GatewayEditResult:
    status: Literal["SUCCEEDED", "PENDING", "FAILED", "CANCELLED"]
    provider: str
    model: str
    provider_request_id: str | None
    output_ref: str | None
    output_mime_type: str | None
    cost_usd: Decimal | None
    cost_confidence: str
    pricing_snapshot_id: str | None
    routing_reason_codes: tuple[str, ...]
    safety_metadata: Mapping[str, object]
    seed: int | None


@dataclass(frozen=True, slots=True)
class EditFinding:
    validator: str
    status: Literal["PASS", "FAIL", "UNAVAILABLE"]
    severity: Severity
    reason_code: str
    score: float | None = None
    threshold: float | None = None
    evidence_ref: str | None = None


@dataclass(frozen=True, slots=True)
class EditValidationReport:
    findings: tuple[EditFinding, ...]
    identity_validation_snapshot_id: str | None = None

    @property
    def hard_failed(self) -> bool:
        return any(item.severity == "HARD" and item.status != "PASS" for item in self.findings)

    @property
    def soft_failed(self) -> bool:
        return any(item.severity == "SOFT" and item.status != "PASS" for item in self.findings)

    @property
    def decision(self) -> Literal["PASS", "REPAIR", "REJECT"]:
        if self.hard_failed:
            return "REJECT"
        if self.soft_failed:
            return "REPAIR"
        return "PASS"


@dataclass(frozen=True, slots=True)
class EditProvenanceSnapshot:
    edit_id: str
    organization_id: str
    operation_id: str
    route: EditRoute
    source_artifact_version_id: str
    source_asset_ref: str
    source_checksum_sha256: str
    instruction_hash: str
    mask_hash: str | None
    protected_region_hash: str
    constraint_snapshot_hash: str
    provider: str | None
    model: str | None
    provider_request_id: str | None
    routing_reason_codes: tuple[str, ...]
    pricing_snapshot_id: str | None
    cost_usd: Decimal | None
    cost_confidence: str | None
    seed: int | None
    code_git_sha: str
    validation_decision: str
    identity_validation_snapshot_id: str | None

    @property
    def snapshot_id(self) -> str:
        return f"image-edit-provenance:{_sha(self)}"


@dataclass(frozen=True, slots=True)
class EditJob:
    edit_id: str
    organization_id: str
    operation_id: str
    semantic_hash: str
    route: EditRoute
    status: EditStatus
    source_artifact_version_id: str
    plan_reason_codes: tuple[str, ...]
    result_artifact_version_id: str | None = None
    result_design_document_version_id: str | None = None
    provider: str | None = None
    model: str | None = None
    provider_request_id: str | None = None
    provenance_snapshot_id: str | None = None
    validation_decision: str | None = None
    error_code: str | None = None
