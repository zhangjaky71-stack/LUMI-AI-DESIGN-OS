from __future__ import annotations

import json
import os
import tempfile
from collections import defaultdict
from dataclasses import replace
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol
from uuid import UUID

from .contracts import (
    IngestionState,
    KnowledgeAccessContext,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSourceType,
    stable_hash,
)


class KnowledgeStore(Protocol):
    def put_document(
        self,
        document: KnowledgeDocument,
        chunks: tuple[KnowledgeChunk, ...],
    ) -> None: ...

    def get_document(self, document_id: str) -> KnowledgeDocument | None: ...

    def get_chunks(self, document_id: str) -> tuple[KnowledgeChunk, ...]: ...

    def visible_candidates(
        self,
        access: KnowledgeAccessContext,
        permission_scopes: tuple[str, ...],
    ) -> Iterable[tuple[KnowledgeDocument, KnowledgeChunk]]: ...

    def get_active_source_document(
        self,
        document: KnowledgeDocument,
    ) -> KnowledgeDocument | None: ...

    def source_history(self, document: KnowledgeDocument) -> tuple[KnowledgeDocument, ...]: ...

    def activate_document(self, document_id: str) -> None: ...

    def mark_deleted(self, document_id: str) -> None: ...


class InMemoryKnowledgeStore:
    """Reference store. Scope selection happens before any retrieval scoring."""

    def __init__(self) -> None:
        self._documents: dict[str, KnowledgeDocument] = {}
        self._chunks: dict[str, KnowledgeChunk] = {}
        self._by_document: dict[str, list[str]] = defaultdict(list)
        self._source_heads: dict[str, str] = {}
        self._source_history: dict[str, list[str]] = defaultdict(list)

    def put_document(
        self,
        document: KnowledgeDocument,
        chunks: tuple[KnowledgeChunk, ...],
    ) -> None:
        if any(chunk.document_id != document.document_id for chunk in chunks):
            raise ValueError("KNOWLEDGE_CHUNK_DOCUMENT_MISMATCH")
        if not chunks:
            raise ValueError("KNOWLEDGE_CHUNKS_REQUIRED")
        existing = self._documents.get(document.document_id)
        if existing is not None and existing != document:
            raise ValueError("KNOWLEDGE_DOCUMENT_IDENTITY_CONFLICT")

        old_ids = self._by_document.get(document.document_id, [])
        for chunk_id in old_ids:
            self._chunks.pop(chunk_id, None)
        self._documents[document.document_id] = document
        self._by_document[document.document_id] = []
        for chunk in chunks:
            self._chunks[chunk.chunk_id] = chunk
            self._by_document[document.document_id].append(chunk.chunk_id)

        source_key = _source_key(document)
        if document.document_id not in self._source_history[source_key]:
            self._source_history[source_key].append(document.document_id)
        self._source_heads[source_key] = document.document_id

    def get_document(self, document_id: str) -> KnowledgeDocument | None:
        return self._documents.get(document_id)

    def get_chunks(self, document_id: str) -> tuple[KnowledgeChunk, ...]:
        return tuple(
            self._chunks[chunk_id]
            for chunk_id in self._by_document.get(document_id, ())
            if chunk_id in self._chunks
        )

    def get_active_source_document(
        self,
        document: KnowledgeDocument,
    ) -> KnowledgeDocument | None:
        head = self._source_heads.get(_source_key(document))
        return self._documents.get(head) if head else None

    def source_history(self, document: KnowledgeDocument) -> tuple[KnowledgeDocument, ...]:
        return tuple(
            self._documents[document_id]
            for document_id in self._source_history.get(_source_key(document), ())
            if document_id in self._documents
        )

    def visible_candidates(
        self,
        access: KnowledgeAccessContext,
        permission_scopes: tuple[str, ...],
    ) -> Iterable[tuple[KnowledgeDocument, KnowledgeChunk]]:
        requested = tuple(scope for scope in permission_scopes if access.allows(scope))
        # Active source heads are selected before lexical/vector scoring.
        for document_id in tuple(self._source_heads.values()):
            document = self._documents.get(document_id)
            if document is None:
                continue
            if document.organization_id != access.organization_id:
                continue
            if document.project_id is not None and document.project_id != access.project_id:
                continue
            if document.brand_id is not None and document.brand_id not in access.brand_ids:
                continue
            if document.permission_scope not in requested and not any(
                _scope_allows(scope, document.permission_scope) for scope in requested
            ):
                continue
            if document.state in {IngestionState.FAILED, IngestionState.DELETED}:
                continue
            for chunk in self.get_chunks(document.document_id):
                yield document, chunk

    def activate_document(self, document_id: str) -> None:
        document = self._documents.get(document_id)
        if document is None:
            raise KeyError("KNOWLEDGE_DOCUMENT_NOT_FOUND")
        if document.state in {IngestionState.FAILED, IngestionState.DELETED}:
            raise ValueError("KNOWLEDGE_DOCUMENT_NOT_ACTIVATABLE")
        self._source_heads[_source_key(document)] = document_id

    def mark_deleted(self, document_id: str) -> None:
        document = self._documents.get(document_id)
        if document is None:
            raise KeyError("KNOWLEDGE_DOCUMENT_NOT_FOUND")
        updated = replace(document, state=IngestionState.DELETED)
        self._documents[document_id] = updated
        source_key = _source_key(document)
        if self._source_heads.get(source_key) == document_id:
            self._source_heads.pop(source_key, None)


class GitWorkspaceKnowledgeStore(InMemoryKnowledgeStore):
    """Atomic JSON persistence without owning Git/network credentials.

    Version manifests are immutable source/index snapshots. A small atomic head file
    chooses which index version is query-active. A crash before the head move leaves the
    previous index active; a crash after the move cannot expose half-written chunks because
    the version manifest is written and fsynced first.
    """

    SCHEMA = "lumi.knowledge-index.v1"

    def __init__(self, root: str | Path) -> None:
        super().__init__()
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._load_existing()

    def put_document(
        self,
        document: KnowledgeDocument,
        chunks: tuple[KnowledgeChunk, ...],
    ) -> None:
        source_dir = self._source_dir(document)
        version_path = source_dir / "versions" / f"{document.document_id}.json"
        payload = {
            "schema": self.SCHEMA,
            "source_key": _source_key(document),
            "document": _serialize_document(document),
            "chunks": [_serialize_chunk(chunk) for chunk in chunks],
        }
        _atomic_json(version_path, payload)
        _atomic_json(
            source_dir / "head.json",
            {
                "schema": self.SCHEMA,
                "source_key": _source_key(document),
                "document_id": document.document_id,
                "deleted": False,
            },
        )
        super().put_document(document, chunks)

    def activate_document(self, document_id: str) -> None:
        document = self.get_document(document_id)
        if document is None:
            raise KeyError("KNOWLEDGE_DOCUMENT_NOT_FOUND")
        if document.state in {IngestionState.FAILED, IngestionState.DELETED}:
            raise ValueError("KNOWLEDGE_DOCUMENT_NOT_ACTIVATABLE")
        _atomic_json(
            self._source_dir(document) / "head.json",
            {
                "schema": self.SCHEMA,
                "source_key": _source_key(document),
                "document_id": document_id,
                "deleted": False,
            },
        )
        super().activate_document(document_id)

    def mark_deleted(self, document_id: str) -> None:
        document = self.get_document(document_id)
        if document is None:
            raise KeyError("KNOWLEDGE_DOCUMENT_NOT_FOUND")
        updated = replace(document, state=IngestionState.DELETED)
        version_path = self._source_dir(document) / "versions" / f"{document_id}.json"
        _atomic_json(
            version_path,
            {
                "schema": self.SCHEMA,
                "source_key": _source_key(updated),
                "document": _serialize_document(updated),
                "chunks": [_serialize_chunk(chunk) for chunk in self.get_chunks(document_id)],
            },
        )
        if self._source_heads.get(_source_key(document)) == document_id:
            _atomic_json(
                self._source_dir(document) / "head.json",
                {
                    "schema": self.SCHEMA,
                    "source_key": _source_key(document),
                    "document_id": document_id,
                    "deleted": True,
                },
            )
        super().mark_deleted(document_id)

    def _source_dir(self, document: KnowledgeDocument) -> Path:
        project = str(document.project_id) if document.project_id else "org"
        scope = document.permission_scope.replace(":", "__")
        source_hash = stable_hash(document.source_ref)[:24]
        return (
            self.root
            / "organizations"
            / str(document.organization_id)
            / project
            / scope
            / "sources"
            / source_hash
        )

    def _load_existing(self) -> None:
        manifests: list[tuple[Path, KnowledgeDocument, tuple[KnowledgeChunk, ...], str]] = []
        for path in sorted(self.root.glob("organizations/**/sources/*/versions/*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if payload.get("schema") != self.SCHEMA:
                    raise ValueError("KNOWLEDGE_STORE_SCHEMA_INVALID")
                document = _deserialize_document(payload["document"])
                chunks = tuple(_deserialize_chunk(value) for value in payload["chunks"])
                source_key = str(payload["source_key"])
                if source_key != _source_key(document):
                    raise ValueError("KNOWLEDGE_STORE_SOURCE_KEY_CORRUPT")
                manifests.append((path, document, chunks, source_key))
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                raise ValueError(f"KNOWLEDGE_STORE_CORRUPT:{path}") from exc

        for _, document, chunks, source_key in manifests:
            if document.document_id in self._documents:
                raise ValueError("KNOWLEDGE_STORE_DUPLICATE_DOCUMENT")
            self._documents[document.document_id] = document
            self._by_document[document.document_id] = []
            for chunk in chunks:
                if chunk.document_id != document.document_id:
                    raise ValueError("KNOWLEDGE_STORE_CHUNK_DOCUMENT_MISMATCH")
                self._chunks[chunk.chunk_id] = chunk
                self._by_document[document.document_id].append(chunk.chunk_id)
            self._source_history[source_key].append(document.document_id)

        for head_path in sorted(self.root.glob("organizations/**/sources/*/head.json")):
            try:
                payload = json.loads(head_path.read_text(encoding="utf-8"))
                if payload.get("schema") != self.SCHEMA:
                    raise ValueError("KNOWLEDGE_STORE_HEAD_SCHEMA_INVALID")
                source_key = str(payload["source_key"])
                document_id = str(payload["document_id"])
                document = self._documents.get(document_id)
                if document is None or _source_key(document) != source_key:
                    raise ValueError("KNOWLEDGE_STORE_HEAD_CORRUPT")
                if not bool(payload.get("deleted", False)):
                    self._source_heads[source_key] = document_id
            except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                raise ValueError(f"KNOWLEDGE_STORE_CORRUPT:{head_path}") from exc


def _source_key(document: KnowledgeDocument) -> str:
    return stable_hash(
        {
            "organization_id": str(document.organization_id),
            "project_id": str(document.project_id) if document.project_id else None,
            "brand_id": document.brand_id,
            "permission_scope": document.permission_scope,
            "source_ref": document.source_ref,
        }
    )


def _scope_allows(granted: str, requested: str) -> bool:
    return granted == requested or granted == requested.split(":", 1)[0]


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".knowledge-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(
                payload,
                handle,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _serialize_document(document: KnowledgeDocument) -> dict[str, Any]:
    return {
        "document_id": document.document_id,
        "organization_id": str(document.organization_id),
        "project_id": str(document.project_id) if document.project_id else None,
        "brand_id": document.brand_id,
        "source_type": document.source_type.value,
        "source_ref": document.source_ref,
        "title": document.title,
        "content_hash": document.content_hash,
        "parser_version": document.parser_version,
        "chunker_version": document.chunker_version,
        "embedding_version": document.embedding_version,
        "index_version": document.index_version,
        "language": document.language,
        "permission_scope": document.permission_scope,
        "state": document.state.value,
        "created_at": document.created_at.isoformat(),
        "observed_at": document.observed_at.isoformat(),
        "source_updated_at": (
            document.source_updated_at.isoformat() if document.source_updated_at else None
        ),
        "metadata": dict(document.metadata),
    }


def _serialize_chunk(chunk: KnowledgeChunk) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "document_id": chunk.document_id,
        "ordinal": chunk.ordinal,
        "text": chunk.text,
        "page": chunk.page,
        "section": chunk.section,
        "token_count": chunk.token_count,
        "content_hash": chunk.content_hash,
        "embedding": list(chunk.embedding),
        "index_version": chunk.index_version,
        "metadata": dict(chunk.metadata),
    }


def _deserialize_document(data: Mapping[str, Any]) -> KnowledgeDocument:
    return KnowledgeDocument(
        document_id=str(data["document_id"]),
        organization_id=UUID(str(data["organization_id"])),
        project_id=UUID(str(data["project_id"])) if data.get("project_id") else None,
        brand_id=str(data["brand_id"]) if data.get("brand_id") else None,
        source_type=KnowledgeSourceType(str(data["source_type"])),
        source_ref=str(data["source_ref"]),
        title=str(data["title"]),
        content_hash=str(data["content_hash"]),
        parser_version=str(data["parser_version"]),
        chunker_version=str(data["chunker_version"]),
        embedding_version=str(data["embedding_version"]),
        index_version=str(data["index_version"]),
        language=str(data["language"]),
        permission_scope=str(data["permission_scope"]),
        state=IngestionState(str(data["state"])),
        created_at=datetime.fromisoformat(str(data["created_at"])),
        observed_at=datetime.fromisoformat(str(data["observed_at"])),
        source_updated_at=(
            datetime.fromisoformat(str(data["source_updated_at"]))
            if data.get("source_updated_at")
            else None
        ),
        metadata=dict(data.get("metadata", {})),
    )


def _deserialize_chunk(data: Mapping[str, Any]) -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id=str(data["chunk_id"]),
        document_id=str(data["document_id"]),
        ordinal=int(data["ordinal"]),
        text=str(data["text"]),
        page=int(data["page"]) if data.get("page") is not None else None,
        section=str(data["section"]) if data.get("section") is not None else None,
        token_count=int(data["token_count"]),
        content_hash=str(data["content_hash"]),
        embedding=tuple(float(value) for value in data["embedding"]),
        index_version=str(data["index_version"]),
        metadata=dict(data.get("metadata", {})),
    )
