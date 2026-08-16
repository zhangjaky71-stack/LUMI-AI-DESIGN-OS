from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from lumi_api.design_ir.primitives import DesignModel, NormalizedRect

ConstraintSeverity = Literal["HARD", "SOFT", "ADVISORY"]
ConstraintSource = Literal[
    "SAFETY_SYSTEM",
    "USER_EXPLICIT",
    "APPROVED_BRAND_RULE",
    "PROJECT_RULE",
    "RECIPE_RULE",
    "AGENT_INFERRED",
    "STYLE_PREFERENCE",
]
ConstraintType = Literal[
    "LOCK_POSITION",
    "LOCK_SIZE",
    "LOCK_ROTATION",
    "LOCK_TRANSFORM",
    "LOCK_ASPECT_RATIO",
    "LOCK_LAYER_ORDER",
    "LOCK_PARENT",
    "LOCK_CONTENT",
    "LOCK_TEXT",
    "LOCK_ASSET",
    "LOCK_IDENTITY",
    "LOCK_STYLE",
    "LOCK_BRAND",
    "PROTECT_REGION",
    "MUST_STAY_INSIDE",
    "MUST_NOT_OVERLAP",
    "MIN_MARGIN",
    "SAFE_AREA",
    "REQUIRE_CONTRAST",
    "REQUIRE_SCANNABILITY",
    "REQUIRE_TEXT_READABILITY",
    "REQUIRE_BRAND_COMPLIANCE",
    "REQUIRE_RESOLUTION",
    "REQUIRE_IDENTITY_SCORE",
]

SOURCE_PRECEDENCE: dict[str, int] = {
    "SAFETY_SYSTEM": 700,
    "USER_EXPLICIT": 600,
    "APPROVED_BRAND_RULE": 500,
    "PROJECT_RULE": 400,
    "RECIPE_RULE": 300,
    "AGENT_INFERRED": 200,
    "STYLE_PREFERENCE": 100,
}


class ConstraintScope(DesignModel):
    node_ids: tuple[UUID, ...] = Field(default=(), max_length=10_000)
    page_ids: tuple[UUID, ...] = Field(default=(), max_length=1_000)
    semantic_tags: tuple[str, ...] = Field(default=(), max_length=64)
    region: NormalizedRect | None = None

    @field_validator("node_ids", "page_ids")
    @classmethod
    def unique_ids(cls, value: tuple[UUID, ...]) -> tuple[UUID, ...]:
        if len(value) != len(set(value)):
            raise ValueError("scope ids must be unique")
        return tuple(sorted(value, key=str))

    @field_validator("semantic_tags")
    @classmethod
    def normalize_tags(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(sorted({item.strip() for item in value if item.strip()}))
        if any(len(item) > 80 for item in normalized):
            raise ValueError("semantic tags must be <= 80 characters")
        return normalized


class Constraint(DesignModel):
    schema_version: str = Field(
        default="lumi.constraint/1.0", pattern=r"^lumi\.constraint/1\.0$"
    )
    id: UUID
    type: ConstraintType
    scope: ConstraintScope = ConstraintScope()
    severity: ConstraintSeverity
    source: ConstraintSource
    priority: int = Field(default=0, ge=0, le=10_000)
    parameters: dict[str, Any] = Field(default_factory=dict)
    active: bool = True

    @field_validator("id")
    @classmethod
    def require_uuid7(cls, value: UUID) -> UUID:
        if value.version != 7:
            raise ValueError("constraint id must be UUIDv7")
        return value

    @property
    def source_precedence(self) -> int:
        return SOURCE_PRECEDENCE[self.source]


class ConstraintSet(DesignModel):
    schema_version: str = Field(
        default="lumi.constraint-set/1.0", pattern=r"^lumi\.constraint-set/1\.0$"
    )
    constraints: tuple[Constraint, ...] = Field(default=(), max_length=50_000)

    @model_validator(mode="after")
    def require_unique_ids(self) -> ConstraintSet:
        ids = [constraint.id for constraint in self.constraints]
        if len(ids) != len(set(ids)):
            raise ValueError("constraint ids must be unique")
        return self


class ConstraintOverride(DesignModel):
    schema_version: str = Field(
        default="lumi.constraint-override/1.0",
        pattern=r"^lumi\.constraint-override/1\.0$",
    )
    override_id: UUID
    constraint_id: UUID
    actor_id: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=3, max_length=2_000)
    occurred_at: datetime
    policy_decision_id: str = Field(min_length=1, max_length=200)

    @field_validator("override_id")
    @classmethod
    def require_uuid7(cls, value: UUID) -> UUID:
        if value.version != 7:
            raise ValueError("override_id must be UUIDv7")
        return value

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        return value


class ConstraintConflict(DesignModel):
    constraint_ids: tuple[UUID, ...] = Field(min_length=2)
    type: ConstraintType
    message_code: Literal["CONSTRAINT_SAME_LEVEL_CONFLICT"] = (
        "CONSTRAINT_SAME_LEVEL_CONFLICT"
    )


class ConstraintViolation(DesignModel):
    schema_version: str = Field(
        default="lumi.constraint-violation/1.0",
        pattern=r"^lumi\.constraint-violation/1\.0$",
    )
    constraint_id: UUID | None
    type: ConstraintType | None
    severity: ConstraintSeverity
    target_id: UUID | None = None
    phase: Literal["preflight", "postflight"]
    expected: dict[str, Any] = Field(default_factory=dict)
    actual: dict[str, Any] = Field(default_factory=dict)
    message_code: str = Field(min_length=1, max_length=200)
    repair_hint: dict[str, Any] = Field(default_factory=dict)
    repairable: bool = False


class EvaluatorContract(DesignModel):
    constraint_type: ConstraintType
    stages: tuple[Literal["preflight", "postflight"], ...]
    preflight_facets: tuple[str, ...] = ()
    postflight_observation_kind: str | None = None


class PostflightObservation(DesignModel):
    schema_version: str = Field(
        default="lumi.constraint-observation/1.0",
        pattern=r"^lumi\.constraint-observation/1\.0$",
    )
    kind: str = Field(min_length=1, max_length=120)
    target_id: UUID | None = None
    region_key: str | None = Field(default=None, max_length=200)
    metrics: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metrics")
    @classmethod
    def reject_non_finite_numbers(cls, value: dict[str, Any]) -> dict[str, Any]:
        def walk(item: Any) -> None:
            if isinstance(item, float) and not (-float("inf") < item < float("inf")):
                raise ValueError("metrics must not contain NaN/Infinity")
            if isinstance(item, dict):
                for child in item.values():
                    walk(child)
            elif isinstance(item, (list, tuple)):
                for child in item:
                    walk(child)

        walk(value)
        return value


class PreflightResult(DesignModel):
    decision: Literal["ALLOW", "ALLOW_WITH_WARNINGS", "DENY"]
    violations: tuple[ConstraintViolation, ...] = ()
    warnings: tuple[ConstraintViolation, ...] = ()
    conflicts: tuple[ConstraintConflict, ...] = ()
    constraint_snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    applied_override_ids: tuple[UUID, ...] = ()


class PostflightResult(DesignModel):
    status: Literal["PASS", "FAIL_REPAIRABLE", "FAIL_HARD"]
    violations: tuple[ConstraintViolation, ...] = ()
    warnings: tuple[ConstraintViolation, ...] = ()
    constraint_snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    applied_override_ids: tuple[UUID, ...] = ()
    can_approve: bool


class ConstrainedApplyResult(DesignModel):
    previous_revision: int
    new_revision: int
    content_hash: str
    changed_node_ids: tuple[UUID, ...]
    constraint_snapshot_hash: str


def active_constraints(constraint_set: ConstraintSet) -> tuple[Constraint, ...]:
    return tuple(constraint for constraint in constraint_set.constraints if constraint.active)


def constraint_snapshot_hash(constraint_set: ConstraintSet) -> str:
    payload = [
        constraint.model_dump(mode="json")
        for constraint in sorted(active_constraints(constraint_set), key=lambda item: str(item.id))
    ]
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
