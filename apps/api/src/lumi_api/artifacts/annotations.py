from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from .models import ArtifactContractModel, CreatedByType


class ArtifactAnnotationType(StrEnum):
    PROVENANCE_CORRECTION = "PROVENANCE_CORRECTION"
    RIGHTS_REVIEW_NOTE = "RIGHTS_REVIEW_NOTE"
    OPERATOR_NOTE = "OPERATOR_NOTE"


class ProvenanceAnnotation(ArtifactContractModel):
    schema_version: str = Field(
        default="lumi.provenance-annotation/1.0",
        pattern=r"^lumi\.provenance-annotation/1\.0$",
    )
    id: UUID
    organization_id: UUID
    artifact_version_id: UUID
    type: ArtifactAnnotationType
    actor_type: CreatedByType
    actor_id: str | None = Field(default=None, max_length=200)
    reason: str = Field(min_length=3, max_length=2_000)
    details: tuple[tuple[str, str], ...] = Field(default=(), max_length=128)
    occurred_at: datetime

    @field_validator("id")
    @classmethod
    def require_uuid7(cls, value: UUID) -> UUID:
        if value.version != 7:
            raise ValueError("provenance annotation id must be UUIDv7")
        return value

    @field_validator("details")
    @classmethod
    def canonicalize_details(
        cls, value: tuple[tuple[str, str], ...]
    ) -> tuple[tuple[str, str], ...]:
        keys = [key for key, _ in value]
        if len(keys) != len(set(keys)):
            raise ValueError("annotation detail keys must be unique")
        if any(not key.strip() or len(key) > 120 for key in keys):
            raise ValueError("annotation detail keys must be non-empty and <=120 chars")
        if any(len(item) > 2_000 for _, item in value):
            raise ValueError("annotation detail values must be <=2000 chars")
        return tuple(sorted(value))

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def actor_identity_is_consistent(self) -> ProvenanceAnnotation:
        if self.actor_type in {CreatedByType.USER, CreatedByType.AGENT} and not self.actor_id:
            raise ValueError("user/agent annotation actor requires actor_id")
        return self
