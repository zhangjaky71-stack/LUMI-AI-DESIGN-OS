from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID

from .errors import ContextSourceValidationError

_HASH = re.compile(r"^[0-9a-f]{64}$")
_REF = re.compile(r"^[a-z][a-z0-9+.-]*://[^\s]{1,2040}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,99}$")
_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}$")
_SCOPE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,255}$")
_MEMORY_SCOPE = re.compile(
    r"^(project|brand|user|organization)(:[A-Za-z0-9_.-]+)?$"
)
_MAX_SOURCE_TEXT = 128_000

CONSTRAINT_TYPES: tuple[str, ...] = (
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
)
_CONSTRAINT_TYPE_SET = frozenset(CONSTRAINT_TYPES)


class ConstraintStrength(StrEnum):
    HARD = "HARD"
    SOFT = "SOFT"
    ADVISORY = "ADVISORY"


class ContextSourceType(StrEnum):
    SAFETY_SYSTEM = "SAFETY_SYSTEM"
    USER_EXPLICIT = "USER_EXPLICIT"
    APPROVED_BRAND_RULE = "APPROVED_BRAND_RULE"
    PROJECT_RULE = "PROJECT_RULE"
    RECIPE_RULE = "RECIPE_RULE"
    AGENT_INFERRED = "AGENT_INFERRED"
    STYLE_PREFERENCE = "STYLE_PREFERENCE"


SOURCE_PRIORITY: tuple[ContextSourceType, ...] = (
    ContextSourceType.SAFETY_SYSTEM,
    ContextSourceType.USER_EXPLICIT,
    ContextSourceType.APPROVED_BRAND_RULE,
    ContextSourceType.PROJECT_RULE,
    ContextSourceType.RECIPE_RULE,
    ContextSourceType.AGENT_INFERRED,
    ContextSourceType.STYLE_PREFERENCE,
)
SOURCE_PRIORITY_RANK = {item: rank for rank, item in enumerate(SOURCE_PRIORITY)}


class ContextScopeKind(StrEnum):
    ORGANIZATION = "organization"
    PROJECT = "project"
    BRAND = "brand"
    USER = "user"
    TASK = "task"


class ContextFactChannel(StrEnum):
    PINNED = "pinned"
    TASK = "task"


@dataclass(frozen=True, slots=True)
class NormalizedRectSnapshot:
    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        values = (self.x, self.y, self.width, self.height)
        if not all(
            isinstance(value, int | float) and math.isfinite(value)
            for value in values
        ):
            raise ContextSourceValidationError("CONTEXT_CONSTRAINT_REGION_INVALID")
        if not (0 <= self.x <= 1 and 0 <= self.y <= 1):
            raise ContextSourceValidationError("CONTEXT_CONSTRAINT_REGION_INVALID")
        if not (0 < self.width <= 1 and 0 < self.height <= 1):
            raise ContextSourceValidationError("CONTEXT_CONSTRAINT_REGION_INVALID")
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ContextSourceValidationError("CONTEXT_CONSTRAINT_REGION_INVALID")

    def canonical_payload(self) -> dict[str, float]:
        return {
            "height": self.height,
            "width": self.width,
            "x": self.x,
            "y": self.y,
        }


@dataclass(frozen=True, slots=True)
class ConstraintScopeSnapshot:
    node_ids: tuple[UUID, ...] = ()
    page_ids: tuple[UUID, ...] = ()
    semantic_tags: tuple[str, ...] = ()
    region: NormalizedRectSnapshot | None = None

    def __post_init__(self) -> None:
        _unique(
            tuple(str(item) for item in self.node_ids),
            "CONTEXT_CONSTRAINT_NODE_SCOPE_DUPLICATE",
        )
        _unique(
            tuple(str(item) for item in self.page_ids),
            "CONTEXT_CONSTRAINT_PAGE_SCOPE_DUPLICATE",
        )
        tags = tuple(item.strip() for item in self.semantic_tags)
        if tags != self.semantic_tags:
            raise ContextSourceValidationError("CONTEXT_CONSTRAINT_TAG_NOT_CANONICAL")
        if any(not item or len(item) > 80 for item in tags):
            raise ContextSourceValidationError("CONTEXT_CONSTRAINT_TAG_INVALID")
        if len(tags) != len(set(tags)):
            raise ContextSourceValidationError("CONTEXT_CONSTRAINT_TAG_DUPLICATE")

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "node_ids": sorted(str(item) for item in self.node_ids),
            "page_ids": sorted(str(item) for item in self.page_ids),
            "region": self.region.canonical_payload() if self.region else None,
            "semantic_tags": sorted(self.semantic_tags),
        }


@dataclass(frozen=True, slots=True)
class ContextConstraint:
    constraint_id: UUID
    constraint_type: str
    strength: ConstraintStrength
    scope: ConstraintScopeSnapshot = field(default_factory=ConstraintScopeSnapshot)
    priority: int = 0
    parameters: Mapping[str, Any] = field(default_factory=dict)
    active: bool = True

    def __post_init__(self) -> None:
        if self.constraint_id.version != 7:
            raise ContextSourceValidationError("CONTEXT_CONSTRAINT_ID_NOT_UUID7")
        if self.constraint_type not in _CONSTRAINT_TYPE_SET:
            raise ContextSourceValidationError("CONTEXT_CONSTRAINT_TYPE_INVALID")
        if not 0 <= self.priority <= 10_000:
            raise ContextSourceValidationError("CONTEXT_CONSTRAINT_PRIORITY_INVALID")
        _json_value(dict(self.parameters), "CONTEXT_CONSTRAINT_PARAMETERS_INVALID")

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "active": self.active,
            "id": str(self.constraint_id),
            "parameters": _normalized(dict(self.parameters)),
            "priority": self.priority,
            "scope": self.scope.canonical_payload(),
            "severity": self.strength.value,
            "type": self.constraint_type,
        }

    def node14_payload(self, source_type: ContextSourceType) -> dict[str, Any]:
        return {
            "active": self.active,
            "id": str(self.constraint_id),
            "parameters": _normalized(dict(self.parameters)),
            "priority": self.priority,
            "schema_version": "lumi.constraint/1.0",
            "scope": self.scope.canonical_payload(),
            "severity": self.strength.value,
            "source": source_type.value,
            "type": self.constraint_type,
        }


@dataclass(frozen=True, slots=True)
class ContextFact:
    key: str
    value: Any
    channel: ContextFactChannel = ContextFactChannel.PINNED

    def __post_init__(self) -> None:
        _key(self.key, "CONTEXT_FACT_KEY_INVALID")
        _json_value(self.value, "CONTEXT_FACT_VALUE_INVALID")

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "channel": self.channel.value,
            "key": self.key,
            "value": _normalized(self.value),
        }


@dataclass(frozen=True, slots=True)
class ContextSourceSnapshot:
    source_ref: str
    source_type: ContextSourceType
    scope_kind: ContextScopeKind
    scope_id: str
    version: str
    constraints: tuple[ContextConstraint, ...] = ()
    facts: tuple[ContextFact, ...] = ()
    source_text: str = ""
    content_hash: str = ""

    def __post_init__(self) -> None:
        _ref(self.source_ref, "CONTEXT_SOURCE_REF_INVALID")
        if not _SCOPE_ID.fullmatch(self.scope_id):
            raise ContextSourceValidationError("CONTEXT_SOURCE_SCOPE_ID_INVALID")
        if not _VERSION.fullmatch(self.version):
            raise ContextSourceValidationError("CONTEXT_SOURCE_VERSION_INVALID")
        if len(self.source_text) > _MAX_SOURCE_TEXT:
            raise ContextSourceValidationError("CONTEXT_SOURCE_TEXT_TOO_LARGE")
        _unique(
            tuple(str(item.constraint_id) for item in self.constraints),
            "CONTEXT_SOURCE_CONSTRAINT_DUPLICATE",
        )
        _unique(
            tuple(f"{item.channel.value}:{item.key}" for item in self.facts),
            "CONTEXT_SOURCE_FACT_DUPLICATE",
        )
        if self.content_hash and not _HASH.fullmatch(self.content_hash):
            raise ContextSourceValidationError("CONTEXT_SOURCE_HASH_INVALID")

    @classmethod
    def build(
        cls,
        *,
        source_ref: str,
        source_type: ContextSourceType,
        scope_kind: ContextScopeKind,
        scope_id: str,
        version: str,
        constraints: tuple[ContextConstraint, ...] = (),
        facts: tuple[ContextFact, ...] = (),
        source_text: str = "",
    ) -> "ContextSourceSnapshot":
        candidate = cls(
            source_ref=source_ref,
            source_type=source_type,
            scope_kind=scope_kind,
            scope_id=scope_id,
            version=version,
            constraints=constraints,
            facts=facts,
            source_text=source_text,
        )
        return cls(
            source_ref=source_ref,
            source_type=source_type,
            scope_kind=scope_kind,
            scope_id=scope_id,
            version=version,
            constraints=constraints,
            facts=facts,
            source_text=source_text,
            content_hash=candidate.expected_content_hash(),
        )

    def canonical_payload(self) -> dict[str, Any]:
        return {
            "constraints": [
                item.canonical_payload()
                for item in sorted(
                    self.constraints, key=lambda value: str(value.constraint_id)
                )
            ],
            "facts": [
                item.canonical_payload()
                for item in sorted(
                    self.facts,
                    key=lambda value: (value.channel.value, value.key),
                )
            ],
            "scope_id": self.scope_id,
            "scope_kind": self.scope_kind.value,
            "source_ref": self.source_ref,
            "source_text": self.source_text,
            "source_type": self.source_type.value,
            "version": self.version,
        }

    def expected_content_hash(self) -> str:
        return sha256_json(self.canonical_payload())


@dataclass(frozen=True, slots=True)
class ContextCompileRequest:
    organization_id: UUID
    project_id: UUID
    task_id: UUID | None
    memory_read_scopes: tuple[str, ...]
    brand_id: str | None = None
    user_id: str | None = None
    version: str = "1"

    def __post_init__(self) -> None:
        if self.brand_id is not None and not _SCOPE_ID.fullmatch(self.brand_id):
            raise ContextSourceValidationError("CONTEXT_BRAND_ID_INVALID")
        if self.user_id is not None and not _SCOPE_ID.fullmatch(self.user_id):
            raise ContextSourceValidationError("CONTEXT_USER_ID_INVALID")
        if not _VERSION.fullmatch(self.version):
            raise ContextSourceValidationError("CONTEXT_BUNDLE_VERSION_INVALID")
        _unique(self.memory_read_scopes, "CONTEXT_MEMORY_SCOPE_DUPLICATE")
        for scope in self.memory_read_scopes:
            if not _MEMORY_SCOPE.fullmatch(scope):
                raise ContextSourceValidationError(
                    f"CONTEXT_MEMORY_SCOPE_INVALID:{scope}"
                )


@dataclass(frozen=True, slots=True)
class CompiledContextBundle:
    context_bundle_ref: str
    version: str
    organization_id: UUID
    project_id: UUID
    task_id: UUID | None
    brand_id: str | None
    user_id: str | None
    required_memory_scopes: tuple[str, ...]
    pinned_constraints: str
    task_context: str
    source_refs: tuple[str, ...]
    source_hashes: tuple[str, ...]
    content_hash: str

    def __post_init__(self) -> None:
        _ref(self.context_bundle_ref, "CONTEXT_BUNDLE_REF_INVALID")
        if not _VERSION.fullmatch(self.version):
            raise ContextSourceValidationError("CONTEXT_BUNDLE_VERSION_INVALID")
        if not _HASH.fullmatch(self.content_hash):
            raise ContextSourceValidationError("CONTEXT_BUNDLE_HASH_INVALID")
        if len(self.source_refs) != len(self.source_hashes):
            raise ContextSourceValidationError("CONTEXT_SOURCE_PROVENANCE_MISMATCH")
        for item in self.source_refs:
            _ref(item, "CONTEXT_SOURCE_REF_INVALID")
        for item in self.source_hashes:
            if not _HASH.fullmatch(item):
                raise ContextSourceValidationError("CONTEXT_SOURCE_HASH_INVALID")

    def canonical_record(self) -> dict[str, Any]:
        return {
            "brand_id": self.brand_id,
            "content_hash": self.content_hash,
            "context_bundle_ref": self.context_bundle_ref,
            "organization_id": str(self.organization_id),
            "pinned_constraints": self.pinned_constraints,
            "project_id": str(self.project_id),
            "required_memory_scopes": list(self.required_memory_scopes),
            "source_hashes": list(self.source_hashes),
            "source_refs": list(self.source_refs),
            "task_context": self.task_context,
            "task_id": str(self.task_id) if self.task_id else None,
            "user_id": self.user_id,
            "version": self.version,
        }


def canonical_json(value: Any) -> str:
    _json_value(value, "CONTEXT_CANONICAL_JSON_INVALID")
    return json.dumps(
        _normalized(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def bundle_content_hash(
    *,
    version: str,
    pinned_constraints: str,
    task_context: str,
    source_refs: tuple[str, ...],
) -> str:
    return sha256_json(
        {
            "pinned_constraints": pinned_constraints,
            "source_refs": list(source_refs),
            "task_context": task_context,
            "version": version,
        }
    )


def _normalized(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _normalized(value[key]) for key in sorted(value)}
    if isinstance(value, tuple | list):
        return [_normalized(item) for item in value]
    return value


def _json_value(value: Any, code: str) -> None:
    if value is None or isinstance(value, bool | int | str):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContextSourceValidationError(code)
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ContextSourceValidationError(code)
            _json_value(item, code)
        return
    if isinstance(value, tuple | list):
        for item in value:
            _json_value(item, code)
        return
    raise ContextSourceValidationError(code)


def _unique(values: tuple[str, ...], code: str) -> None:
    if len(values) != len(set(values)):
        raise ContextSourceValidationError(code)


def _key(value: str, code: str) -> None:
    if not _KEY.fullmatch(value):
        raise ContextSourceValidationError(code)


def _ref(value: str, code: str) -> None:
    if not _REF.fullmatch(value):
        raise ContextSourceValidationError(code)
