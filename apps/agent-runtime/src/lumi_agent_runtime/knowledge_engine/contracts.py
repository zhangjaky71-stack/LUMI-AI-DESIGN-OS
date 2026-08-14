from __future__ import annotations

import hashlib
import json
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
    INDEXING = "INDEXING"
    READY = "READY"
    SUPERSEDED = "SUPERSEDED"
    FAILED = "FAILED"
    DELETED = "DELETED"


class KnowledgeTrust(StrEnum):
    INTERNAL_DATA = "INTERNAL_DATA"
    USER_CONTENT = "USER_CONTENT"
    EXTERNAL_UNTRUSTED = "EXTERNAL_UNTRUSTED"
    MODEL_GENERATED = "MODEL_GENERATED"


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

    def __post_init__(self) -> None:
        if not self.source_id or not self.version:
            raise ValueError("KNOWLEDGE_SOURCE_IDENTITY_INVALID")
        if len(self.content_hash) < 32:
            raise ValueError("KNOWLEDGE_SOURCE_HASH_INVALID")


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    document_id: UUID
    organization_id: UUID
    project_id: UUID | None
    source: KnowledgeSourceRef
    trust: KnowledgeTrust
    status: KnowledgeStatus
    normalized_text: str
    language: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    version: int = 1

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
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.ordinal < 0 or self.token_estimate < 1 or not self.text:
            raise ValueError("KNOWLEDGE_CHUNK_INVALID")
        if hashlib.sha256(self.text.encode()).hexdigest() != self.content_hash:
            raise ValueError("KNOWLEDGE_CHUNK_HASH_MISMATCH")
        if (self.embedding is None) != (self.embedding_model is None):
            raise ValueError("KNOWLEDGE_CHUNK_EMBEDDING_IDENTITY_INVALID")
        if self.embedding is not None and not self.embedding_version:
            raise ValueError("KNOWLEDGE_CHUNK_EMBEDDING_VERSION_REQUIRED")


@dataclass(frozen=True, slots=True)
class KnowledgeSearchQuery:
    access: KnowledgeAccessContext
    text: str
    limit: int = 12
    query_embedding: tuple[float, ...] | None = None
    source_types: tuple[KnowledgeSourceType, ...] = ()

    def __post_init__(self) -> None:
        if not self.text.strip() or not 1 <= self.limit <= 50:
            raise ValueError("KNOWLEDGE_SEARCH_QUERY_INVALID")


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


@dataclass(frozen=True, slots=True)
class KnowledgeIndexRequest:
    access: KnowledgeAccessContext
    source: KnowledgeSourceRef
    trust: KnowledgeTrust
    normalized_text: str
    project_id: UUID | None
    language: str | None = None
    chunk_size_tokens: int = 450
    chunk_overlap_tokens: int = 60
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.normalized_text.strip():
            raise ValueError("KNOWLEDGE_INDEX_TEXT_EMPTY")
        if not 100 <= self.chunk_size_tokens <= 2000:
            raise ValueError("KNOWLEDGE_CHUNK_SIZE_INVALID")
        if not 0 <= self.chunk_overlap_tokens < self.chunk_size_tokens:
            raise ValueError("KNOWLEDGE_CHUNK_OVERLAP_INVALID")
        if self.project_id is not None and self.access.project_id != self.project_id:
            raise ValueError("KNOWLEDGE_INDEX_PROJECT_SCOPE_DENIED")

    @property
    def semantic_hash(self) -> str:
        payload = {
            "organization_id": str(self.access.organization_id),
            "project_id": str(self.project_id) if self.project_id else None,
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
            "chunk_size_tokens": self.chunk_size_tokens,
            "chunk_overlap_tokens": self.chunk_overlap_tokens,
            "metadata": self.metadata,
        }
        return hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ).encode()
        ).hexdigest()
