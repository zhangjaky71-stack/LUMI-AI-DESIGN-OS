from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal, Mapping

from .contracts_common import (
    EditRoute,
    EditStatus,
    Severity,
    ValidationDecision,
    _canonical,
    canonical_hash,
)
from .contracts_spec import ProtectedRegion


@dataclass(frozen=True, slots=True)
class GatewayEditRequest:
    organization_id: str
    project_id: str
    task_id: str
    operation_id: str
    edit_id: str
    route: EditRoute
    source_ref: str
    mask_ref: str | None
    instruction: str
    required_capabilities: tuple[str, ...]
    protected_regions: tuple[ProtectedRegion, ...]
    reference_asset_refs: tuple[str, ...]
    budget_limit_usd: Decimal
    seed: int | None

    def __post_init__(self) -> None:
        if "://" in self.source_ref:
            raise ValueError("IMAGE_EDIT_GATEWAY_SOURCE_REF_URL_FORBIDDEN")
        if self.mask_ref and "://" in self.mask_ref:
            raise ValueError("IMAGE_EDIT_GATEWAY_MASK_REF_URL_FORBIDDEN")
        if not self.budget_limit_usd.is_finite() or self.budget_limit_usd < 0:
            raise ValueError("IMAGE_EDIT_GATEWAY_BUDGET_INVALID")


@dataclass(frozen=True, slots=True)
class GatewayEditResult:
    status: Literal["SUCCEEDED", "PENDING", "FAILED", "CANCELLED"]
    provider: str
    model: str
    provider_request_id: str | None = None
    output_ref: str | None = None
    output_mime_type: str | None = None
    cost_usd: Decimal | None = None
    cost_confidence: str = "unknown"
    pricing_snapshot_id: str | None = None
    routing_reason_codes: tuple[str, ...] = ()
    safety_metadata: Mapping[str, object] = field(default_factory=dict)
    model_revision: str | None = None
    registry_snapshot_id: str | None = None
    seed: int | None = None
    finish_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.provider or not self.model:
            raise ValueError("IMAGE_EDIT_PROVIDER_MODEL_REQUIRED")
        if self.status == "PENDING" and not self.provider_request_id:
            raise ValueError("IMAGE_EDIT_PENDING_PROVIDER_REQUEST_ID_REQUIRED")
        if self.status == "SUCCEEDED" and not self.output_ref:
            raise ValueError("IMAGE_EDIT_SUCCEEDED_OUTPUT_REQUIRED")
        if (
            self.cost_usd is not None
            and (not self.cost_usd.is_finite() or self.cost_usd < 0)
        ):
            raise ValueError("IMAGE_EDIT_COST_INVALID")
        _canonical(self.safety_metadata)


@dataclass(frozen=True, slots=True)
class ValidatedImage:
    bucket: str
    storage_key: str
    checksum_sha256: str
    mime_type: str
    width: int
    height: int
    size_bytes: int
    asset_id: str | None = None

    def __post_init__(self) -> None:
        if not self.bucket or not self.storage_key or "://" in self.storage_key:
            raise ValueError("IMAGE_EDIT_DURABLE_OUTPUT_KEY_REQUIRED")
        if len(self.checksum_sha256) != 64:
            raise ValueError("IMAGE_EDIT_OUTPUT_CHECKSUM_INVALID")
        if min(self.width, self.height) <= 0 or self.size_bytes < 0:
            raise ValueError("IMAGE_EDIT_OUTPUT_METADATA_INVALID")

    @property
    def durable_ref(self) -> str:
        return f"{self.bucket}/{self.storage_key}"


@dataclass(frozen=True, slots=True)
class EditFinding:
    validator: str
    status: Literal["PASS", "FAIL", "UNAVAILABLE"]
    severity: Severity
    reason_code: str
    score: float | None = None
    threshold: float | None = None
    evidence_ref: str | None = None

    def __post_init__(self) -> None:
        for value in (self.score, self.threshold):
            if value is not None and not math.isfinite(value):
                raise ValueError("IMAGE_EDIT_FINDING_NON_FINITE")


@dataclass(frozen=True, slots=True)
class EditValidationReport:
    findings: tuple[EditFinding, ...]
    identity_validation_snapshot_id: str | None = None

    @property
    def hard_failed(self) -> bool:
        return any(
            finding.severity == "HARD" and finding.status != "PASS"
            for finding in self.findings
        )

    @property
    def soft_failed(self) -> bool:
        return any(
            finding.severity == "SOFT" and finding.status != "PASS"
            for finding in self.findings
        )

    @property
    def decision(self) -> ValidationDecision:
        if self.hard_failed:
            return "REJECT"
        if self.soft_failed:
            return "REPAIR"
        return "PASS"


@dataclass(frozen=True, slots=True)
class EditProvenance:
    edit_id: str
    operation_id: str
    route: EditRoute
    source_artifact_version_id: str
    source_checksum_sha256: str
    instruction_hash: str
    mask_hash: str | None
    protected_region_hash: str
    constraint_snapshot_hash: str
    provider: str | None
    model: str | None
    model_revision: str | None
    registry_snapshot_id: str | None
    provider_request_id: str | None
    routing_reason_codes: tuple[str, ...]
    pricing_snapshot_id: str | None
    cost_usd: Decimal | None
    cost_confidence: str | None
    seed: int | None
    agent_run_id: str | None
    agent_version: str | None
    recipe_version: str | None
    skill_versions: Mapping[str, str]
    code_git_sha: str
    validation_decision: str
    identity_validation_snapshot_id: str | None
    safety_metadata: Mapping[str, object] = field(default_factory=dict)
    finish_reason: str | None = None

    def __post_init__(self) -> None:
        if self.cost_usd is not None and (
            not self.cost_usd.is_finite() or self.cost_usd < 0
        ):
            raise ValueError("IMAGE_EDIT_PROVENANCE_COST_INVALID")
        _canonical(self.skill_versions)
        _canonical(self.safety_metadata)

    @property
    def snapshot_id(self) -> str:
        return "image-edit-provenance:" + canonical_hash(self)


@dataclass(frozen=True, slots=True)
class ArtifactEditResult:
    artifact_id: str
    artifact_version_id: str
    status: str
    asset_id: str


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
    result_asset_id: str | None = None
    provider: str | None = None
    model: str | None = None
    provider_request_id: str | None = None
    provenance_snapshot_id: str | None = None
    validation_decision: str | None = None
    error_code: str | None = None
