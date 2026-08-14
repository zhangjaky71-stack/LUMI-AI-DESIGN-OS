from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Protocol

from .model import (
    EditJob,
    EditPlan,
    EditProvenanceSnapshot,
    EditValidationReport,
    GatewayEditResult,
    ImageEditSpec,
    MaskSpec,
    SourceImageRef,
    StructuralEditOperation,
)


@dataclass(frozen=True, slots=True)
class StructuralEditResult:
    design_document_version_id: str
    artifact_version_id: str | None
    applied_operation_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StoredEditedImage:
    storage_key: str
    checksum_sha256: str
    mime_type: str
    size_bytes: int
    width: int
    height: int
    durable_asset_ref: str

    def __post_init__(self) -> None:
        if not self.storage_key or "://" in self.storage_key:
            raise ValueError("IMAGE_EDIT_STORAGE_KEY_MUST_BE_DURABLE")
        if len(self.checksum_sha256) != 64:
            raise ValueError("IMAGE_EDIT_OUTPUT_CHECKSUM_INVALID")
        if self.size_bytes <= 0:
            raise ValueError("IMAGE_EDIT_OUTPUT_SIZE_INVALID")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("IMAGE_EDIT_OUTPUT_DIMENSIONS_INVALID")
        if not self.mime_type.startswith("image/"):
            raise ValueError("IMAGE_EDIT_OUTPUT_MIME_INVALID")
        if not self.durable_asset_ref or "://" in self.durable_asset_ref:
            raise ValueError("IMAGE_EDIT_DURABLE_ASSET_REF_INVALID")


@dataclass(frozen=True, slots=True)
class ArtifactEditResult:
    artifact_version_id: str
    status: str


class StructuralEditPort(Protocol):
    async def apply(
        self,
        *,
        spec: ImageEditSpec,
        operations: tuple[StructuralEditOperation, ...],
    ) -> StructuralEditResult: ...


class EditModelGatewayPort(Protocol):
    async def invoke(self, *, spec: ImageEditSpec, plan: EditPlan, mask: MaskSpec | None) -> GatewayEditResult: ...

    async def poll(
        self,
        *,
        spec: ImageEditSpec,
        plan: EditPlan,
        pending: GatewayEditResult,
        mask: MaskSpec | None,
    ) -> GatewayEditResult: ...


class EditedOutputPort(Protocol):
    async def materialize_and_store(
        self,
        *,
        spec: ImageEditSpec,
        output_ref: str,
        declared_mime_type: str | None,
    ) -> StoredEditedImage: ...


class EditValidationPort(Protocol):
    async def validate(
        self,
        *,
        spec: ImageEditSpec,
        plan: EditPlan,
        candidate: StoredEditedImage,
    ) -> EditValidationReport: ...


class ProtectedCompositePort(Protocol):
    async def composite_source_regions(
        self,
        *,
        source: SourceImageRef,
        candidate: StoredEditedImage,
        spec: ImageEditSpec,
    ) -> StoredEditedImage: ...


class ArtifactEditPort(Protocol):
    async def create_version(
        self,
        *,
        spec: ImageEditSpec,
        candidate: StoredEditedImage,
        provenance: EditProvenanceSnapshot,
        validation: EditValidationReport,
    ) -> ArtifactEditResult: ...


class EditCostPort(Protocol):
    async def record(
        self,
        *,
        edit_id: str,
        operation_id: str,
        provider: str,
        model: str,
        provider_request_id: str | None,
        amount_usd: Decimal | None,
        confidence: str,
        pricing_snapshot_id: str | None,
    ) -> None: ...


class EditEventPort(Protocol):
    async def emit(
        self,
        event_type: str,
        *,
        organization_id: str,
        edit_id: str,
        payload: Mapping[str, object],
    ) -> None: ...


class EditRepositoryPort(Protocol):
    def get_by_operation(self, organization_id: str, operation_id: str) -> EditJob | None: ...
    def save(self, job: EditJob) -> None: ...
    def save_spec(self, spec: ImageEditSpec) -> None: ...
    def get_spec(self, organization_id: str, operation_id: str) -> ImageEditSpec | None: ...
    def save_pending(self, organization_id: str, edit_id: str, result: GatewayEditResult) -> None: ...
    def get_pending(self, organization_id: str, edit_id: str) -> GatewayEditResult | None: ...
    def delete_pending(self, organization_id: str, edit_id: str) -> None: ...
