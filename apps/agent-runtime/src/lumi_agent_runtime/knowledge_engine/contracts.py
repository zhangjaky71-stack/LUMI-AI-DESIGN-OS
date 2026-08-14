from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class KnowledgeSourceType(StrEnum):
    ASSET = "ASSET"
    URL = "URL"
    TEXT = "TEXT"
    ARTIFACT = "ARTIFACT"
    INTERNAL_DOCUMENT = "INTERNAL_DOCUMENT"


class KnowledgeStatus(StrEnum):
    PENDING = "PENDING"
    EXTRACTING = "EXTRACTING"
    CHUNKING = "CHUNKING"
    EMBEDDING = "EMBEDDING"
    READY = "READY"
    FAILED = "FAILED"
    STALE = "STALE"
    SUPERSEDED = "SUPERSEDED"
    DELETED = "DELETED"


class KnowledgeTrust(StrEnum):
    INTERNAL_DATA = "INTERNAL_DATA"
    USER_CONTENT = "USER_CONTENT"
    EXTERNAL_UNTRUSTED = "EXTERNAL_UNTRUSTED"
    MODEL_GENERATED = "MODEL_GENERATED"


class KnowledgePermissionScope(StrEnum):
    PROJECT = "PROJECT"
    ORGANIZATION = "ORGANIZATION"


@dataclass(frozen=True, slots=True)
class KnowledgeAccessContext:
    organization_id: UUID
    project_id: UUID | None
    actor_id: str
    granted_permissions: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class KnowledgeSourceRef:
    source_type: KnowledgeSourceType
    source_id: str
    version: str
    content_hash: str
    title: str | None = None
    uri: str | None = None
    observed_at: datetime | None = None
    source_updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.source_id or not self.version:
            raise ValueError("KNOWLEDGE_SOURCE_IDENTITY_INVALID")
        if len(self.content_hash) < 32:
            raise ValueError("KNOWLEDGE_SOURCE_HASH_INVALID")


@dataclass(frozen=True, slots=True)
class KnowledgeSegment:
    text: str
    page: int | None = None
    section: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("KNOWLEDGE_SEGMENT_TEXT_EMPTY")
        if self.page is not None and self.page < 1:
            raise ValueError("KNOWLEDGE_SEGMENT_PAGE_INVALID")


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    document_id: UUID
    organization_id: UUID
    project_id: UUID | None
    source: KnowledgeSourceRef
    permission_scope: KnowledgePermissionScope
    trust: KnowledgeTrust
    status: KnowledgeStatus
    normalized_text: str
    parser_version: str
    chunker_version: str
    index_version: str
    language: str | None = None
    embedding_space_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    version: int = 1

    def __post_init__(self) -> None:
        if (
            self.status
            not in {
                KnowledgeStatus.PENDING,
                KnowledgeStatus.EXTRACTING,
                KnowledgeStatus.FAILED,
            }
            and not self.normalized_text.strip()
        ):
            raise ValueError("KNOWLEDGE_DOCUMENT_TEXT_EMPTY")
        if not self.parser_version or not self.chunker_version or not self.index_version:
            raise ValueError("KNOWLEDGE_DOCUMENT_INDEX_IDENTITY_INVALID")
        _validate_scope(self.permission_scope, self.project_id)
        if self.version < 1:
            raise ValueError("KNOWLEDGE_DOCUMENT_VERSION_INVALID")

    @property
    def scope_key(self) -> str:
        return _scope_key(self.permission_scope, self.project_id)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.normalized_text.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    chunk_id: UUID
    document_id: UUID
    organization_id: UUID
    project_id: UUID | None
    ordinal: int
    text: str
    content_hash: str
    token_estimate: int
    locator: dict[str, Any]
    source: KnowledgeSourceRef
    trust: KnowledgeTrust
    embedding: tuple[float, ...] | None = None
    embedding_model: str | None = None
    embedding_version: str | None = None
    embedding_space_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.ordinal < 0 or self.token_estimate < 1 or not self.text:
            raise ValueError("KNOWLEDGE_CHUNK_INVALID")
        if hashlib.sha256(self.text.encode()).hexdigest() != self.content_hash:
            raise ValueError("KNOWLEDGE_CHUNK_HASH_MISMATCH")
        if self.embedding is None:
            if any(
                value is not None
                for value in (
                    self.embedding_model,
                    self.embedding_version,
                    self.embedding_space_id,
                )
            ):
                raise ValueError("KNOWLEDGE_CHUNK_EMBEDDING_IDENTITY_INVALID")
        else:
            if not all(
                (
                    self.embedding_model,
                    self.embedding_version,
                    self.embedding_space_id,
                )
            ):
                raise ValueError("KNOWLEDGE_CHUNK_EMBEDDING_IDENTITY_INVALID")
            if not self.embedding or len(self.embedding) > 8192:
                raise ValueError("KNOWLEDGE_CHUNK_EMBEDDING_INVALID")
            if any(not math.isfinite(float(value)) for value in self.embedding):
                raise ValueError("KNOWLEDGE_CHUNK_EMBEDDING_INVALID")


@dataclass(frozen=True, slots=True)
class KnowledgeSearchQuery:
    access: KnowledgeAccessContext
    text: str
    limit: int = 12
    query_embedding: tuple[float, ...] | None = None
    query_embedding_space_id: str | None = None
    source_types: tuple[KnowledgeSourceType, ...] = ()
    expanded_queries: tuple[str, ...] = ()
    require_fresh: bool = False
    max_source_age_seconds: int | None = None
    now: datetime | None = None

    def __post_init__(self) -> None:
        if not self.text.strip() or not 1 <= self.limit <= 50:
            raise ValueError("KNOWLEDGE_SEARCH_QUERY_INVALID")
        if (self.query_embedding is None) != (self.query_embedding_space_id is None):
            raise ValueError("KNOWLEDGE_QUERY_EMBEDDING_IDENTITY_INVALID")
        if self.max_source_age_seconds is not None and self.max_source_age_seconds < 1:
            raise ValueError("KNOWLEDGE_FRESHNESS_WINDOW_INVALID")
        if self.require_fresh and self.max_source_age_seconds is None:
            raise ValueError("KNOWLEDGE_FRESHNESS_WINDOW_REQUIRED")
        if any(not item.strip() for item in self.expanded_queries):
            raise ValueError("KNOWLEDGE_EXPANDED_QUERY_INVALID")


@dataclass(frozen=True, slots=True)
class KnowledgeCitation:
    source_type: str
    source_id: str
    source_version: str
    source_hash: str
    document_id: UUID
    chunk_id: UUID
    locator: dict[str, Any]
    title: str | None = None
    uri: str | None = None


@dataclass(frozen=True, slots=True)
class KnowledgeSearchResult:
    chunk: KnowledgeChunk
    score: float
    lexical_score: float
    semantic_score: float
    freshness_score: float
    authority_score: float
    citation: KnowledgeCitation
    stale: bool = False


@dataclass(frozen=True, slots=True)
class KnowledgeIngestRequest:
    access: KnowledgeAccessContext
    source: KnowledgeSourceRef
    trust: KnowledgeTrust
    project_id: UUID | None
    permission_scope: KnowledgePermissionScope = KnowledgePermissionScope.PROJECT
    chunker_version: str = "structure-window-v1"
    index_version: str = "knowledge-v1"
    embedding_space_id: str | None = None
    chunk_size_tokens: int = 450
    chunk_overlap_tokens: int = 60
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_index_scope(
            access=self.access,
            permission_scope=self.permission_scope,
            project_id=self.project_id,
        )
        _validate_chunk_config(
            chunk_size_tokens=self.chunk_size_tokens,
            chunk_overlap_tokens=self.chunk_overlap_tokens,
        )
        if not self.chunker_version or not self.index_version:
            raise ValueError("KNOWLEDGE_INGEST_VERSION_REQUIRED")

    @property
    def scope_key(self) -> str:
        return _scope_key(self.permission_scope, self.project_id)

    @property
    def config_hash(self) -> str:
        payload = {
            "organization_id": str(self.access.organization_id),
            "scope_key": self.scope_key,
            "source_type": self.source.source_type.value,
            "source_id": self.source.source_id,
            "source_version": self.source.version,
            "source_hash": self.source.content_hash,
            "trust": self.trust.value,
            "chunker_version": self.chunker_version,
            "index_version": self.index_version,
            "embedding_space_id": self.embedding_space_id,
            "chunk_size_tokens": self.chunk_size_tokens,
            "chunk_overlap_tokens": self.chunk_overlap_tokens,
            "metadata": self.metadata,
        }
        return _hash_payload(payload)


@dataclass(frozen=True, slots=True)
class KnowledgeIndexRequest:
    access: KnowledgeAccessContext
    source: KnowledgeSourceRef
    trust: KnowledgeTrust
    normalized_text: str
    project_id: UUID | None
    permission_scope: KnowledgePermissionScope = KnowledgePermissionScope.PROJECT
    language: str | None = None
    parser_version: str = "native-text-v1"
    chunker_version: str = "structure-window-v1"
    index_version: str = "knowledge-v1"
    embedding_space_id: str | None = None
    chunk_size_tokens: int = 450
    chunk_overlap_tokens: int = 60
    segments: tuple[KnowledgeSegment, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.normalized_text.strip():
            raise ValueError("KNOWLEDGE_INDEX_TEXT_EMPTY")
        _validate_index_scope(
            access=self.access,
            permission_scope=self.permission_scope,
            project_id=self.project_id,
        )
        _validate_chunk_config(
            chunk_size_tokens=self.chunk_size_tokens,
            chunk_overlap_tokens=self.chunk_overlap_tokens,
        )
        if not self.parser_version or not self.chunker_version or not self.index_version:
            raise ValueError("KNOWLEDGE_INDEX_VERSION_REQUIRED")

    @property
    def scope_key(self) -> str:
        return _scope_key(self.permission_scope, self.project_id)

    @property
    def semantic_hash(self) -> str:
        payload = {
            "organization_id": str(self.access.organization_id),
            "project_id": str(self.project_id) if self.project_id else None,
            "scope_key": self.scope_key,
            "permission_scope": self.permission_scope.value,
            "source": {
                "type": self.source.source_type.value,
                "id": self.source.source_id,
                "version": self.source.version,
                "hash": self.source.content_hash,
            },
            "trust": self.trust.value,
            "normalized_text_hash": hashlib.sha256(
                self.normalized_text.encode()
            ).hexdigest(),
            "language": self.language,
            "parser_version": self.parser_version,
            "chunker_version": self.chunker_version,
            "index_version": self.index_version,
            "embedding_space_id": self.embedding_space_id,
            "chunk_size_tokens": self.chunk_size_tokens,
            "chunk_overlap_tokens": self.chunk_overlap_tokens,
            "segments": [
                {
                    "text_hash": hashlib.sha256(segment.text.encode()).hexdigest(),
                    "page": segment.page,
                    "section": segment.section,
                    "metadata": segment.metadata,
                }
                for segment in self.segments
            ],
            "metadata": self.metadata,
        }
        return _hash_payload(payload)


def _validate_index_scope(
    *,
    access: KnowledgeAccessContext,
    permission_scope: KnowledgePermissionScope,
    project_id: UUID | None,
) -> None:
    if project_id is not None and access.project_id != project_id:
        raise ValueError("KNOWLEDGE_INDEX_PROJECT_SCOPE_DENIED")
    if permission_scope == KnowledgePermissionScope.PROJECT:
        if project_id is None or access.project_id != project_id:
            raise ValueError("KNOWLEDGE_INDEX_PROJECT_SCOPE_DENIED")
        return
    if project_id is not None:
        raise ValueError("KNOWLEDGE_INDEX_ORGANIZATION_PROJECT_FORBIDDEN")
    if "knowledge.organization.write" not in access.granted_permissions:
        raise ValueError("KNOWLEDGE_INDEX_ORGANIZATION_SCOPE_DENIED")


def _validate_scope(
    permission_scope: KnowledgePermissionScope,
    project_id: UUID | None,
) -> None:
    if permission_scope == KnowledgePermissionScope.PROJECT:
        if project_id is None:
            raise ValueError("KNOWLEDGE_PROJECT_SCOPE_REQUIRES_PROJECT")
    elif project_id is not None:
        raise ValueError("KNOWLEDGE_ORGANIZATION_SCOPE_FORBIDS_PROJECT")


def _scope_key(
    permission_scope: KnowledgePermissionScope,
    project_id: UUID | None,
) -> str:
    _validate_scope(permission_scope, project_id)
    if permission_scope == KnowledgePermissionScope.PROJECT:
        assert project_id is not None
        return f"PROJECT:{project_id}"
    return "ORGANIZATION"


def _validate_chunk_config(
    *,
    chunk_size_tokens: int,
    chunk_overlap_tokens: int,
) -> None:
    if not 100 <= chunk_size_tokens <= 2000:
        raise ValueError("KNOWLEDGE_CHUNK_SIZE_INVALID")
    if not 0 <= chunk_overlap_tokens < chunk_size_tokens:
        raise ValueError("KNOWLEDGE_CHUNK_OVERLAP_INVALID")


def _hash_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
