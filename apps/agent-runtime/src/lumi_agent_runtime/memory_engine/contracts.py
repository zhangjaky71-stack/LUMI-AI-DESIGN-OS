from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class MemoryScope(StrEnum):
    SESSION = "SESSION"
    USER = "USER"
    PROJECT = "PROJECT"
    BRAND = "BRAND"
    AGENT = "AGENT"
    ORGANIZATION = "ORGANIZATION"


class MemoryKind(StrEnum):
    PREFERENCE = "PREFERENCE"
    FACT = "FACT"
    DECISION = "DECISION"
    CONSTRAINT_PREFERENCE = "CONSTRAINT_PREFERENCE"
    WORKFLOW_LEARNING = "WORKFLOW_LEARNING"
    EPISODIC_SUMMARY = "EPISODIC_SUMMARY"


class MemoryStatus(StrEnum):
    ACTIVE = "ACTIVE"
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
    SUPERSEDED = "SUPERSEDED"
    DELETED = "DELETED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"


class MemoryActorType(StrEnum):
    USER = "USER"
    AGENT = "AGENT"
    SYSTEM = "SYSTEM"


class MemorySensitivity(StrEnum):
    NONE = "NONE"
    CREDENTIAL = "CREDENTIAL"
    PAYMENT = "PAYMENT"
    HEALTH = "HEALTH"
    OTHER_SENSITIVE = "OTHER_SENSITIVE"


class MemoryCandidateOutcome(StrEnum):
    WRITE = "WRITE"
    DEDUPLICATE_CONFIRM = "DEDUPLICATE_CONFIRM"
    REQUIRE_CONFIRMATION = "REQUIRE_CONFIRMATION"
    BRAND_RULE_PROPOSAL = "BRAND_RULE_PROPOSAL"
    REJECT_SENSITIVE = "REJECT_SENSITIVE"
    REJECT_SCOPE = "REJECT_SCOPE"


@dataclass(frozen=True, slots=True)
class MemorySourceRef:
    source_type: str
    source_id: str
    version: str
    content_hash: str

    def __post_init__(self) -> None:
        if not self.source_type or not self.source_id or not self.version:
            raise ValueError("MEMORY_SOURCE_REF_INVALID")
        if len(self.content_hash) < 32:
            raise ValueError("MEMORY_SOURCE_HASH_INVALID")


@dataclass(frozen=True, slots=True)
class MemoryAccessContext:
    organization_id: UUID
    actor_type: MemoryActorType
    actor_id: str
    project_id: UUID | None = None
    user_id: UUID | None = None
    brand_id: UUID | None = None
    agent_key: str | None = None
    session_id: str | None = None
    granted_permissions: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    candidate_id: UUID
    organization_id: UUID
    scope_type: MemoryScope
    scope_id: str
    kind: MemoryKind
    semantic_key: str
    content_structured: dict[str, Any]
    summary: str
    source_refs: tuple[MemorySourceRef, ...]
    confidence: float
    created_by_type: MemoryActorType
    created_by_id: str
    explicit_remember: bool = False
    temporal_coexistence: bool = False
    proposed_at: datetime | None = None
    expires_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.scope_id or len(self.scope_id) > 512:
            raise ValueError("MEMORY_SCOPE_ID_INVALID")
        if not self.semantic_key or len(self.semantic_key) > 512:
            raise ValueError("MEMORY_SEMANTIC_KEY_INVALID")
        if not self.summary or len(self.summary) > 8000:
            raise ValueError("MEMORY_SUMMARY_INVALID")
        if not 0 <= self.confidence <= 1:
            raise ValueError("MEMORY_CONFIDENCE_INVALID")
        if not self.source_refs:
            raise ValueError("MEMORY_SOURCE_REF_REQUIRED")
        _json_guard(self.content_structured, "$.content_structured")
        _json_guard(self.metadata, "$.metadata")

    @property
    def content_hash(self) -> str:
        payload = {
            "scope_type": self.scope_type.value,
            "scope_id": self.scope_id,
            "kind": self.kind.value,
            "semantic_key": self.semantic_key,
            "content_structured": self.content_structured,
            "summary": self.summary,
        }
        return _hash_payload(payload)


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    memory_id: UUID
    organization_id: UUID
    scope_type: MemoryScope
    scope_id: str
    kind: MemoryKind
    semantic_key: str
    content_structured: dict[str, Any]
    summary: str
    source_refs: tuple[MemorySourceRef, ...]
    confidence: float
    status: MemoryStatus
    created_by_type: MemoryActorType
    created_by_id: str
    created_at: datetime
    last_confirmed_at: datetime | None = None
    expires_at: datetime | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    supersedes_id: UUID | None = None
    version: int = 1
    retention_hold: bool = False
    deleted_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.scope_id or not self.semantic_key or not self.summary:
            raise ValueError("MEMORY_RECORD_IDENTITY_INVALID")
        if not 0 <= self.confidence <= 1 or self.version < 1:
            raise ValueError("MEMORY_RECORD_VERSION_CONFIDENCE_INVALID")
        _json_guard(self.content_structured, "$.content_structured")
        _json_guard(self.metadata, "$.metadata")

    @property
    def content_hash(self) -> str:
        return _hash_payload(
            {
                "scope_type": self.scope_type.value,
                "scope_id": self.scope_id,
                "kind": self.kind.value,
                "semantic_key": self.semantic_key,
                "content_structured": self.content_structured,
                "summary": self.summary,
            }
        )


@dataclass(frozen=True, slots=True)
class MemoryDecision:
    outcome: MemoryCandidateOutcome
    candidate_id: UUID
    record: MemoryRecord | None = None
    existing_record_id: UUID | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class MemorySearchQuery:
    access: MemoryAccessContext
    text: str
    limit: int = 12
    scope_types: tuple[MemoryScope, ...] = ()
    kind: MemoryKind | None = None
    query_embedding: tuple[float, ...] | None = None

    def __post_init__(self) -> None:
        if not self.text or not 1 <= self.limit <= 50:
            raise ValueError("MEMORY_SEARCH_QUERY_INVALID")


@dataclass(frozen=True, slots=True)
class MemorySearchResult:
    record: MemoryRecord
    score: float
    lexical_score: float
    semantic_score: float
    scope_score: float
    confidence_score: float
    freshness_score: float


def _hash_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _json_guard(value: Any, path: str, depth: int = 0) -> None:
    if depth > 8:
        raise ValueError(f"MEMORY_JSON_DEPTH_EXCEEDED:{path}")
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, list):
        if len(value) > 512:
            raise ValueError(f"MEMORY_JSON_LIST_TOO_LARGE:{path}")
        for index, item in enumerate(value):
            _json_guard(item, f"{path}[{index}]", depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > 256:
            raise ValueError(f"MEMORY_JSON_OBJECT_TOO_LARGE:{path}")
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 256:
                raise ValueError(f"MEMORY_JSON_KEY_INVALID:{path}")
            _json_guard(item, f"{path}.{key}", depth + 1)
        return
    raise ValueError(f"MEMORY_JSON_TYPE_INVALID:{path}")
