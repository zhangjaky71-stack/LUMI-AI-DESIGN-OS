from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Mapping
from uuid import UUID

_HASH = re.compile(r"^[0-9a-f]{64}$")
_REF = re.compile(r"^[a-z][a-z0-9+.-]*://[^\s]{1,2040}$")
_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,254}$")
_SUBJECT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,254}$")
_FORBIDDEN_METADATA_KEYS = {
    "chain_of_thought",
    "chain-of-thought",
    "reasoning",
    "private_reasoning",
    "scratchpad",
    "cot",
}


class MemoryScopeKind(StrEnum):
    PROJECT = "project"
    BRAND = "brand"
    USER = "user"
    ORGANIZATION = "organization"


class MemoryKind(StrEnum):
    FACT = "fact"
    PREFERENCE = "preference"
    DECISION = "decision"
    EPISODE = "episode"
    SUMMARY = "summary"
    ARTIFACT_NOTE = "artifact_note"


class MemoryStatus(StrEnum):
    ACTIVE = "active"
    TOMBSTONE = "tombstone"


@dataclass(frozen=True, slots=True)
class MemoryScope:
    kind: MemoryScopeKind
    subject_id: str | None = None

    def __post_init__(self) -> None:
        if self.subject_id is not None and not _SUBJECT.fullmatch(self.subject_id):
            raise ValueError("MEMORY_SCOPE_SUBJECT_INVALID")
        if self.kind in {MemoryScopeKind.BRAND, MemoryScopeKind.USER} and not self.subject_id:
            raise ValueError("MEMORY_SCOPE_SUBJECT_REQUIRED")

    @property
    def permission_key(self) -> str:
        if self.subject_id is None:
            return self.kind.value
        return f"{self.kind.value}:{self.subject_id}"

    def resolved(self, *, organization_id: UUID, project_id: UUID) -> "MemoryScope":
        if self.subject_id is not None:
            return self
        if self.kind is MemoryScopeKind.PROJECT:
            return MemoryScope(self.kind, str(project_id))
        if self.kind is MemoryScopeKind.ORGANIZATION:
            return MemoryScope(self.kind, str(organization_id))
        return self


@dataclass(frozen=True, slots=True)
class MemoryAccessContext:
    organization_id: UUID
    project_id: UUID
    actor_id: str
    read_scopes: tuple[str, ...]
    write_scopes: tuple[str, ...]
    agent_run_id: UUID | None = None
    task_id: UUID | None = None

    def __post_init__(self) -> None:
        if not self.actor_id or len(self.actor_id) > 255:
            raise ValueError("MEMORY_ACTOR_INVALID")
        _unique(self.read_scopes, "MEMORY_READ_SCOPE_DUPLICATE")
        _unique(self.write_scopes, "MEMORY_WRITE_SCOPE_DUPLICATE")
        for scope in self.read_scopes + self.write_scopes:
            _validate_permission_scope(scope)
        if not _permission_subset(self.write_scopes, self.read_scopes):
            raise ValueError("MEMORY_WRITE_SCOPE_ESCALATION")

    @classmethod
    def from_runtime(cls, *, invocation: Any, agent: Any) -> "MemoryAccessContext":
        read = _intersection_scopes(
            tuple(agent.memory_read_scopes),
            tuple(invocation.permissions.memory_read_scopes),
        )
        write = _intersection_scopes(
            tuple(agent.memory_write_scopes),
            tuple(invocation.permissions.memory_write_scopes),
        )
        return cls(
            organization_id=invocation.organization_id,
            project_id=invocation.project_id,
            actor_id=invocation.actor_id,
            read_scopes=read,
            write_scopes=write,
            agent_run_id=invocation.agent_run_id,
            task_id=invocation.task_id,
        )


@dataclass(frozen=True, slots=True)
class MemoryWriteRequest:
    scope: MemoryScope
    memory_key: str
    kind: MemoryKind
    content: str
    confidence: float
    importance: float = 0.5
    source_refs: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    idempotency_key: str = ""
    expected_parent_ref: str | None = None
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        if not _KEY.fullmatch(self.memory_key):
            raise ValueError("MEMORY_KEY_INVALID")
        if not self.content or len(self.content) > 64_000:
            raise ValueError("MEMORY_CONTENT_INVALID")
        for value in (self.confidence, self.importance):
            if not isinstance(value, int | float) or not math.isfinite(value):
                raise ValueError("MEMORY_SCORE_INVALID")
            if not 0 <= float(value) <= 1:
                raise ValueError("MEMORY_SCORE_INVALID")
        _unique(self.source_refs, "MEMORY_SOURCE_REF_DUPLICATE")
        for ref in self.source_refs:
            if not _REF.fullmatch(ref):
                raise ValueError("MEMORY_SOURCE_REF_INVALID")
        if self.idempotency_key and not _KEY.fullmatch(self.idempotency_key):
            raise ValueError("MEMORY_IDEMPOTENCY_KEY_INVALID")
        if (
            self.expected_parent_ref is not None
            and not self.expected_parent_ref.startswith("memory://")
        ):
            raise ValueError("MEMORY_PARENT_REF_INVALID")
        if self.expires_at is not None:
            if self.expires_at.tzinfo is None:
                raise ValueError("MEMORY_EXPIRY_TIMEZONE_REQUIRED")
        _metadata_guard(dict(self.metadata))


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    organization_id: UUID
    project_id: UUID | None
    scope: MemoryScope
    memory_key: str
    kind: MemoryKind
    status: MemoryStatus
    revision: int
    content: str
    confidence: float
    importance: float
    source_refs: tuple[str, ...]
    metadata: Mapping[str, Any]
    parent_ref: str | None
    content_hash: str
    actor_id: str
    agent_run_id: UUID | None
    task_id: UUID | None
    created_at: datetime
    expires_at: datetime | None = None
    idempotency_key: str = ""

    def __post_init__(self) -> None:
        if self.revision < 1:
            raise ValueError("MEMORY_REVISION_INVALID")
        if not _HASH.fullmatch(self.content_hash):
            raise ValueError("MEMORY_CONTENT_HASH_INVALID")
        if self.parent_ref is not None and not self.parent_ref.startswith("memory://"):
            raise ValueError("MEMORY_PARENT_REF_INVALID")
        if self.created_at.tzinfo is None:
            raise ValueError("MEMORY_CREATED_TIMEZONE_REQUIRED")
        if self.status is MemoryStatus.TOMBSTONE and self.content:
            raise ValueError("MEMORY_TOMBSTONE_CONTENT_FORBIDDEN")

    @property
    def memory_ref(self) -> str:
        project = str(self.project_id) if self.project_id else "org"
        scope = self.scope.permission_key.replace(":", "/")
        return (
            f"memory://{self.organization_id}/{project}/{scope}/"
            f"{self.memory_key}/r{self.revision}/{self.content_hash}"
        )

    @property
    def expired(self) -> bool:
        if self.expires_at is None:
            return False
        return self.expires_at <= datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class MemorySearchRequest:
    query: str
    scopes: tuple[str, ...]
    limit: int = 12
    kinds: tuple[MemoryKind, ...] = ()

    def __post_init__(self) -> None:
        if len(self.query) > 32_000:
            raise ValueError("MEMORY_SEARCH_QUERY_INVALID")
        if not 1 <= self.limit <= 100:
            raise ValueError("MEMORY_SEARCH_LIMIT_INVALID")
        _unique(self.scopes, "MEMORY_SEARCH_SCOPE_DUPLICATE")
        for scope in self.scopes:
            _validate_permission_scope(scope)


@dataclass(frozen=True, slots=True)
class MemoryHit:
    record: MemoryRecord
    lexical_score: float
    recency_score: float

    @property
    def rank_score(self) -> float:
        return min(
            1.0,
            0.44 * self.lexical_score
            + 0.22 * self.recency_score
            + 0.18 * self.record.confidence
            + 0.16 * self.record.importance,
        )


def memory_content_hash(
    *,
    organization_id: UUID,
    project_id: UUID | None,
    scope: MemoryScope,
    memory_key: str,
    kind: MemoryKind,
    status: MemoryStatus,
    content: str,
    confidence: float,
    importance: float,
    source_refs: tuple[str, ...],
    metadata: Mapping[str, Any],
    parent_ref: str | None,
    expires_at: datetime | None,
) -> str:
    payload = {
        "organization_id": str(organization_id),
        "project_id": str(project_id) if project_id else None,
        "scope": scope.permission_key,
        "memory_key": memory_key,
        "kind": kind.value,
        "status": status.value,
        "content": content,
        "confidence": round(float(confidence), 8),
        "importance": round(float(importance), 8),
        "source_refs": list(source_refs),
        "metadata": dict(metadata),
        "parent_ref": parent_ref,
        "expires_at": expires_at.isoformat() if expires_at else None,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def permission_allows(granted: tuple[str, ...], requested: str) -> bool:
    requested_kind = requested.split(":", 1)[0]
    return requested in granted or requested_kind in granted


def scope_is_visible(scope: MemoryScope, access: MemoryAccessContext) -> bool:
    resolved = scope.resolved(
        organization_id=access.organization_id,
        project_id=access.project_id,
    )
    return permission_allows(access.read_scopes, resolved.permission_key)


def _validate_permission_scope(value: str) -> None:
    parts = value.split(":", 1)
    try:
        kind = MemoryScopeKind(parts[0])
    except ValueError as exc:
        raise ValueError(f"MEMORY_SCOPE_INVALID:{value}") from exc
    if len(parts) == 2 and not _SUBJECT.fullmatch(parts[1]):
        raise ValueError(f"MEMORY_SCOPE_INVALID:{value}")
    if kind in {MemoryScopeKind.BRAND, MemoryScopeKind.USER} and len(parts) == 1:
        return


def _permission_subset(child: tuple[str, ...], parent: tuple[str, ...]) -> bool:
    return all(permission_allows(parent, item) for item in child)


def _intersection_scopes(left: tuple[str, ...], right: tuple[str, ...]) -> tuple[str, ...]:
    output: list[str] = []
    for item in left:
        if permission_allows(right, item):
            output.append(item)
            continue
        kind = item.split(":", 1)[0]
        exact = [candidate for candidate in right if candidate.startswith(f"{kind}:")]
        output.extend(candidate for candidate in exact if permission_allows(left, candidate))
    return tuple(dict.fromkeys(output))


def _metadata_guard(value: Any, depth: int = 0) -> None:
    if depth > 20:
        raise ValueError("MEMORY_METADATA_TOO_DEEP")
    if value is None or isinstance(value, str | int | bool):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("MEMORY_METADATA_NONFINITE")
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("MEMORY_METADATA_KEY_INVALID")
            if key.lower() in _FORBIDDEN_METADATA_KEYS:
                raise ValueError("MEMORY_PRIVATE_REASONING_FORBIDDEN")
            _metadata_guard(child, depth + 1)
        return
    if isinstance(value, tuple | list):
        for child in value:
            _metadata_guard(child, depth + 1)
        return
    raise ValueError(f"MEMORY_METADATA_TYPE_INVALID:{type(value).__name__}")


def _unique(values: tuple[Any, ...], code: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(code)
