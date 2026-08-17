from __future__ import annotations

from typing import Protocol

from .model import (
    ArtifactEditResult,
    EditJob,
    EditProvenance,
    EditValidationReport,
    GatewayEditRequest,
    GatewayEditResult,
    ImageEditSpec,
    SourceImageRef,
    StructuralEditOperation,
    ValidatedImage,
)


class SourceAuthorizationPort(Protocol):
    def authorize_current(self, spec: ImageEditSpec) -> SourceImageRef: ...


class StructuralEditPort(Protocol):
    async def apply(
        self,
        spec: ImageEditSpec,
        operations: tuple[StructuralEditOperation, ...],
    ) -> str: ...


class ImageEditGatewayPort(Protocol):
    async def invoke(self, request: GatewayEditRequest) -> GatewayEditResult: ...

    async def poll(
        self,
        request: GatewayEditRequest,
        pending: GatewayEditResult,
    ) -> GatewayEditResult: ...

    async def cancel(self, pending: GatewayEditResult) -> bool: ...


class OutputMaterializerPort(Protocol):
    async def materialize(
        self,
        *,
        spec: ImageEditSpec,
        edit_id: str,
        result: GatewayEditResult,
    ) -> ValidatedImage: ...


class PostflightPort(Protocol):
    async def validate(
        self,
        *,
        spec: ImageEditSpec,
        image: ValidatedImage,
        source: SourceImageRef,
    ) -> EditValidationReport: ...


class ProtectedCompositorPort(Protocol):
    async def composite(
        self,
        *,
        spec: ImageEditSpec,
        generated: ValidatedImage,
        source: SourceImageRef,
    ) -> ValidatedImage: ...


class ArtifactEditPort(Protocol):
    async def append_candidate(
        self,
        *,
        spec: ImageEditSpec,
        image: ValidatedImage,
        provenance: EditProvenance,
        validation: EditValidationReport,
    ) -> ArtifactEditResult: ...


class CanvasUpdatePort(Protocol):
    async def replace_asset(
        self,
        *,
        spec: ImageEditSpec,
        asset_id: str,
    ) -> str: ...


class EditRepositoryPort(Protocol):
    def get_by_operation(
        self,
        org: str,
        operation_id: str,
    ) -> EditJob | None: ...

    def get(self, org: str, edit_id: str) -> EditJob | None: ...

    def save_spec(self, spec: ImageEditSpec) -> None: ...

    def get_spec(self, org: str, edit_id: str) -> ImageEditSpec: ...

    def save(self, job: EditJob) -> None: ...

    def save_pending(
        self,
        edit_id: str,
        request: GatewayEditRequest,
        result: GatewayEditResult,
    ) -> None: ...

    def get_pending(
        self,
        edit_id: str,
    ) -> tuple[GatewayEditRequest, GatewayEditResult] | None: ...

    def delete_pending(self, edit_id: str) -> None: ...


class EditCostProjectionPort(Protocol):
    async def record(
        self,
        *,
        edit_id: str,
        operation_id: str,
        result: GatewayEditResult,
    ) -> None: ...


class EditAuditPort(Protocol):
    async def record(
        self,
        *,
        provenance: EditProvenance,
        validation: EditValidationReport,
    ) -> None: ...


class EventSinkPort(Protocol):
    async def emit(
        self,
        event_type: str,
        *,
        organization_id: str,
        edit_id: str,
        payload: dict[str, object],
    ) -> None: ...
