from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

CanvasOperationType = Literal[
    "CREATE_NODE",
    "DELETE_NODE",
    "SET_PROPERTY",
    "MOVE_NODE",
    "RESIZE_NODE",
    "ROTATE_NODE",
    "REORDER_NODE",
    "REPARENT_NODE",
    "REPLACE_ASSET",
    "SET_TEXT",
]


class CanvasOperationDescriptorRequest(BaseModel):
    type: CanvasOperationType
    target_ids: list[str] = Field(default_factory=list, max_length=256)
    payload: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("target_ids")
    @classmethod
    def canonical_targets(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value]
        if any(not item for item in cleaned):
            raise ValueError("CANVAS_TARGET_ID_EMPTY")
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("CANVAS_TARGET_ID_DUPLICATE")
        return cleaned


class CanvasCommandBatchRequest(BaseModel):
    client_batch_id: UUID
    expected_design_document_version_id: UUID
    expected_version_number: int = Field(ge=1)
    expected_revision: int = Field(ge=1)
    descriptors: list[CanvasOperationDescriptorRequest] = Field(min_length=1, max_length=128)


class CanvasDocumentProjectionResponse(BaseModel):
    design_document_id: UUID
    design_document_version_id: UUID
    version_number: int = Field(ge=1)
    revision: int = Field(ge=1)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    active_page_id: UUID
    document: dict[str, Any]

    @model_validator(mode="after")
    def projection_identity_matches(self) -> "CanvasDocumentProjectionResponse":
        if self.document.get("document_id") != str(self.design_document_id):
            raise ValueError("CANVAS_PROJECTION_DOCUMENT_ID_MISMATCH")
        metadata = self.document.get("metadata")
        if not isinstance(metadata, dict):
            raise ValueError("CANVAS_PROJECTION_METADATA_REQUIRED")
        if metadata.get("document_version") != self.revision:
            raise ValueError("CANVAS_PROJECTION_REVISION_MISMATCH")
        return self


class CanvasCommandBatchResponse(BaseModel):
    client_batch_id: UUID
    projection: CanvasDocumentProjectionResponse
    applied_descriptors: int = Field(ge=1, le=128)