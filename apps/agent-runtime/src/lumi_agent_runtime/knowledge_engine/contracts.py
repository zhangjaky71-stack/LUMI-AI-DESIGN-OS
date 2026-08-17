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
_SCOPE = re.compile(r"^(project|brand|organization)(:[A-Za-z0-9_.-]+)?$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,99}$")


class IngestionState(StrEnum):
    PENDING = "PENDING"
    EXTRACTING = "EXTRACTING"
    CHUNKING = "CHUNKING"
    EMBEDDING = "EMBEDDING"
    READY = "READY"
    FAILED = "FAILED"
    STALE = "STALE"
    DELETED = "DELETED"


class KnowledgeSourceType(StrEnum):
    UPLOADED_DOCUMENT = "uploaded_document"
    WEB_SNAPSHOT = "web_snapshot"
    BRAND_GUIDE = "brand_guide"
    PRODUCT_INFO = "product_info"
    PROJECT_NOTE = "project_note"
    APPROVED_RESEARCH = "approved_research"


class KnowledgeScopeKind(StrEnum):
    PROJECT = "project"
    BRAND = "brand"
    ORGANIZATION = "organization"


@dataclass(frozen=True, slots=True)
class KnowledgeAccessContext:
    organization_id: UUID
    project_id: UUID
    actor_id: str
    read_scopes: tuple[str, ...]
    brand_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.actor_id or len(self.actor_id) > 255:
            raise ValueError("KNOWLEDGE_ACTOR_INVALID")
        _unique(self.read_scopes, "KNOWLEDGE_READ_SCOPE_DUPLICATE")
        _unique(self.brand_ids, "KNOWLEDGE_BRAND_DUPLICATE")
        for scope in self.read_scopes:
            if not _SCOPE.fullmatch(scope):
                raise ValueError(f"KNOWLEDGE_SCOPE_INVALID:{scope}")

    def allows(self, permission_scope: str) -> bool:
        kind = permission_scope.split(":", 1)[0]
        if permission_scope in self.read_scopes or kind in self.read_scopes:
            return True
        if permission_scope.startswith("brand:"):
            return permission_scope.split(":", 1)[1] in self.brand_ids
        return False


@dataclass(frozen=True, slots=True)
class SourceSection:
    text: str
    page: int | None = None
    section: str | None = None

    def __post_init__(self) -> None:
        if not self.text.strip() or len(self.text) > 2_000_000:
            raise ValueError("KNOWLEDGE_SECTION_TEXT_INVALID")
        if self.page is not None and self.page < 1:
            raise ValueError("KNOWLEDGE_SECTION_PAGE_INVALID")
        if self.section is not None and len(self.section) > 500:
            raise ValueError("KNOWLEDGE_SECTION_NAME_INVALID")


@dataclass(frozen=True, slots=True)
class KnowledgeIngestRequest:
    source_type: KnowledgeSourceType
    source_ref: str
    title: str
    parser_version: str
    language: str
    permission_scope: str
    sections: tuple[SourceSection, ...]
    organization_id: UUID
    project_id: UUID | None = None
    brand_id: str | None = None
    source_updated_at: datetime | None = None
    observed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _REF.fullmatch(self.source_ref):
            raise ValueError("KNOWLEDGE_SOURCE_REF_INVALID")
        if not self.title.strip() or len(self.title) > 1_000:
            raise ValueError("KNOWLEDGE_TITLE_INVALID")
        if not _VERSION.fullmatch(self.parser_version):
            raise ValueError("KNOWLEDGE_PARSER_VERSION_INVALID")
        if not self.language or len(self.language) > 32:
            raise ValueError("KNOWLEDGE_LANGUAGE_INVALID")
        if not _SCOPE.fullmatch(self.permission_scope):
            raise ValueError("KNOWLEDGE_PERMISSION_SCOPE_INVALID")
        if self.permission_scope == "project" and self.project_id is None:
            raise ValueError("KNOWLEDGE_PROJECT_SCOPE_PROJECT_REQUIRED")
        if self.permission_scope.startswith("brand:"):
            scoped_brand = self.permission_scope.split(":", 1)[1]
            if self.brand_id != scoped_brand:
                raise ValueError("KNOWLEDGE_BRAND_SCOPE_MISMATCH")
        if not self.sections:
            raise ValueError("KNOWLEDGE_SECTIONS_REQUIRED")
        if self.observed_at.tzinfo is None:
            raise ValueError("KNOWLEDGE_OBSERVED_TIMEZONE_REQUIRED")
        if self.source_updated_at is not None and self.source_updated_at.tzinfo is None:
            raise ValueError("KNOWLEDGE_UPDATED_TIMEZONE_REQUIRED")
        _json_guard(dict(self.metadata))


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    document_id: str
    organization_id: UUID
    project_id: UUID | None
    brand_id: str | None
    source_type: KnowledgeSourceType
    source_ref: str
    title: str
    content_hash: str
    parser_version: str
    chunker_version: str
    embedding_version: str
    index_version: str
    language: str
    permission_scope: str
    state: IngestionState
    created_at: datetime
    observed_at: datetime
    source_updated_at: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.document_id.startswith("kdoc_"):
            raise ValueError("KNOWLEDGE_DOCUMENT_ID_INVALID")
        if not _HASH.fullmatch(self.content_hash):
            raise ValueError("KNOWLEDGE_CONTENT_HASH_INVALID")
        for version in (
            self.parser_version,
            self.chunker_version,
            self.embedding_version,
            self.index_version,
        ):
            if not _VERSION.fullmatch(version):
                raise ValueError("KNOWLEDGE_VERSION_INVALID")
        if not _SCOPE.fullmatch(self.permission_scope):
            raise ValueError("KNOWLEDGE_PERMISSION_SCOPE_INVALID")
        if self.created_at.tzinfo is None or self.observed_at.tzinfo is None:
            raise ValueError("KNOWLEDGE_TIMEZONE_REQUIRED")


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    chunk_id: str
    document_id: str
    ordinal: int
    text: str
    page: int | None
    section: str | None
    token_count: int
    content_hash: str
    embedding: tuple[float, ...]
    index_version: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.chunk_id.startswith("kchunk_"):
            raise ValueError("KNOWLEDGE_CHUNK_ID_INVALID")
        if self.ordinal < 0 or self.token_count < 1:
            raise ValueError("KNOWLEDGE_CHUNK_ORDINAL_INVALID")
        if not self.text.strip():
            raise ValueError("KNOWLEDGE_CHUNK_TEXT_INVALID")
        if self.page is not None and self.page < 1:
            raise ValueError("KNOWLEDGE_CHUNK_PAGE_INVALID")
        if not _HASH.fullmatch(self.content_hash):
            raise ValueError("KNOWLEDGE_CHUNK_HASH_INVALID")
        if not self.embedding:
            raise ValueError("KNOWLEDGE_EMBEDDING_REQUIRED")
        if any(not math.isfinite(value) for value in self.embedding):
            raise ValueError("KNOWLEDGE_EMBEDDING_NONFINITE")
        if not _VERSION.fullmatch(self.index_version):
            raise ValueError("KNOWLEDGE_INDEX_VERSION_INVALID")
        _json_guard(dict(self.metadata))


@dataclass(frozen=True, slots=True)
class KnowledgeSearchRequest:
    query: str
    permission_scopes: tuple[str, ...]
    limit: int = 12
    query_expansions: tuple[str, ...] = ()
    include_stale: bool = True
    max_chunks_per_document: int = 3

    def __post_init__(self) -> None:
        if not self.query.strip() or len(self.query) > 32_000:
            raise ValueError("KNOWLEDGE_SEARCH_QUERY_INVALID")
        if not 1 <= self.limit <= 100:
            raise ValueError("KNOWLEDGE_SEARCH_LIMIT_INVALID")
        if not 1 <= self.max_chunks_per_document <= 10:
            raise ValueError("KNOWLEDGE_DIVERSITY_LIMIT_INVALID")
        _unique(self.permission_scopes, "KNOWLEDGE_SEARCH_SCOPE_DUPLICATE")
        for scope in self.permission_scopes:
            if not _SCOPE.fullmatch(scope):
                raise ValueError(f"KNOWLEDGE_SCOPE_INVALID:{scope}")
        for expansion in self.query_expansions:
            if not expansion.strip() or len(expansion) > 4_000:
                raise ValueError("KNOWLEDGE_QUERY_EXPANSION_INVALID")


@dataclass(frozen=True, slots=True)
class KnowledgeCitation:
    document_id: str
    chunk_id: str
    source_ref: str
    title: str
    page: int | None
    section: str | None
    content_hash: str

    def __post_init__(self) -> None:
        if not _REF.fullmatch(self.source_ref):
            raise ValueError("KNOWLEDGE_CITATION_SOURCE_REF_INVALID")
        if not _HASH.fullmatch(self.content_hash):
            raise ValueError("KNOWLEDGE_CITATION_HASH_INVALID")


@dataclass(frozen=True, slots=True)
class KnowledgeHit:
    chunk: KnowledgeChunk
    document: KnowledgeDocument
    citation: KnowledgeCitation
    lexical_score: float
    vector_score: float
    fusion_score: float
    freshness_score: float
    stale: bool

    @property
    def rank_score(self) -> float:
        return min(
            1.0,
            max(0.0, 0.58 * self.fusion_score + 0.22 * self.freshness_score + 0.20),
        )


@dataclass(frozen=True, slots=True)
class KnowledgeSearchResult:
    original_query: str
    query_expansions: tuple[str, ...]
    hits: tuple[KnowledgeHit, ...]
    searched_index_versions: tuple[str, ...]
    warnings: tuple[str, ...] = ()


def stable_hash(value: Any) -> str:
    payload = json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def document_content_hash(request: KnowledgeIngestRequest) -> str:
    return stable_hash(
        {
            "source_ref": request.source_ref,
            "parser_version": request.parser_version,
            "language": request.language,
            "sections": [
                {"page": item.page, "section": item.section, "text": item.text}
                for item in request.sections
            ],
        }
    )


def cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    lnorm = math.sqrt(sum(value * value for value in left))
    rnorm = math.sqrt(sum(value * value for value in right))
    if lnorm == 0 or rnorm == 0:
        return 0.0
    return max(-1.0, min(1.0, dot / (lnorm * rnorm)))


def tokenize(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"[\w\u3400-\u9fff]+", text.lower()))


def _json_guard(value: Any, depth: int = 0) -> None:
    if depth > 24:
        raise ValueError("KNOWLEDGE_JSON_TOO_DEEP")
    if value is None or isinstance(value, str | int | bool):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("KNOWLEDGE_JSON_NONFINITE")
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("KNOWLEDGE_JSON_NON_STRING_KEY")
            _json_guard(child, depth + 1)
        return
    if isinstance(value, tuple | list):
        for child in value:
            _json_guard(child, depth + 1)
        return
    if isinstance(value, UUID | StrEnum | datetime):
        return
    raise ValueError(f"KNOWLEDGE_JSON_UNSUPPORTED:{type(value).__name__}")


def _jsonable(value: Any) -> Any:
    _json_guard(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(value[key]) for key in sorted(value)}
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    if isinstance(value, UUID | StrEnum):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _unique(values: tuple[Any, ...], code: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(code)
