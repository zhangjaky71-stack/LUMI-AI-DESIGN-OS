from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Callable

from .contracts import (
    MemoryAccessContext,
    MemoryHit,
    MemoryKind,
    MemoryRecord,
    MemoryScope,
    MemoryScopeKind,
    MemorySearchRequest,
    MemoryStatus,
    MemoryWriteRequest,
    memory_content_hash,
    permission_allows,
)
from .errors import MemoryConflictError, MemoryNotFoundError, MemoryPermissionError
from .store import MemoryStore

_TOKEN = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]+")


class MemoryEngine:
    def __init__(
        self,
        store: MemoryStore,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    async def write(
        self,
        request: MemoryWriteRequest,
        *,
        access: MemoryAccessContext,
    ) -> MemoryRecord:
        scope = request.scope.resolved(
            organization_id=access.organization_id,
            project_id=access.project_id,
        )
        self._authorize(scope, access.write_scopes, "MEMORY_WRITE_DENIED")
        project_id = _storage_project_id(scope, access.project_id)
        if request.idempotency_key:
            existing = await self.store.get_by_idempotency(
                organization_id=access.organization_id,
                idempotency_key=request.idempotency_key,
            )
            if existing is not None:
                if _same_request(existing, request, scope, project_id):
                    return existing
                raise MemoryConflictError("MEMORY_IDEMPOTENCY_CONFLICT")
        head = await self.store.get_head(
            organization_id=access.organization_id,
            project_id=project_id,
            scope_key=scope.permission_key,
            memory_key=request.memory_key,
        )
        expected = request.expected_parent_ref
        if expected is not None and (head is None or head.memory_ref != expected):
            raise MemoryConflictError("MEMORY_EXPECTED_PARENT_MISMATCH")
        parent_ref = head.memory_ref if head else None
        revision = head.revision + 1 if head else 1
        created_at = self.clock()
        content_hash = memory_content_hash(
            organization_id=access.organization_id,
            project_id=project_id,
            scope=scope,
            memory_key=request.memory_key,
            kind=request.kind,
            status=MemoryStatus.ACTIVE,
            content=request.content,
            confidence=request.confidence,
            importance=request.importance,
            source_refs=request.source_refs,
            metadata=request.metadata,
            parent_ref=parent_ref,
            expires_at=request.expires_at,
        )
        record = MemoryRecord(
            organization_id=access.organization_id,
            project_id=project_id,
            scope=scope,
            memory_key=request.memory_key,
            kind=request.kind,
            status=MemoryStatus.ACTIVE,
            revision=revision,
            content=request.content,
            confidence=float(request.confidence),
            importance=float(request.importance),
            source_refs=request.source_refs,
            metadata=dict(request.metadata),
            parent_ref=parent_ref,
            content_hash=content_hash,
            actor_id=access.actor_id,
            agent_run_id=access.agent_run_id,
            task_id=access.task_id,
            created_at=created_at,
            expires_at=request.expires_at,
            idempotency_key=request.idempotency_key,
        )
        return await self.store.append(record, expected_parent_ref=parent_ref)

    async def forget(
        self,
        *,
        scope: MemoryScope,
        memory_key: str,
        access: MemoryAccessContext,
        expected_parent_ref: str | None = None,
        source_refs: tuple[str, ...] = (),
    ) -> MemoryRecord:
        resolved = scope.resolved(
            organization_id=access.organization_id,
            project_id=access.project_id,
        )
        self._authorize(resolved, access.write_scopes, "MEMORY_FORGET_DENIED")
        project_id = _storage_project_id(resolved, access.project_id)
        head = await self.store.get_head(
            organization_id=access.organization_id,
            project_id=project_id,
            scope_key=resolved.permission_key,
            memory_key=memory_key,
        )
        if head is None:
            raise MemoryNotFoundError("MEMORY_NOT_FOUND")
        if expected_parent_ref is not None and head.memory_ref != expected_parent_ref:
            raise MemoryConflictError("MEMORY_EXPECTED_PARENT_MISMATCH")
        content_hash = memory_content_hash(
            organization_id=access.organization_id,
            project_id=project_id,
            scope=resolved,
            memory_key=memory_key,
            kind=head.kind,
            status=MemoryStatus.TOMBSTONE,
            content="",
            confidence=0.0,
            importance=0.0,
            source_refs=source_refs,
            metadata={},
            parent_ref=head.memory_ref,
            expires_at=None,
        )
        record = MemoryRecord(
            organization_id=access.organization_id,
            project_id=project_id,
            scope=resolved,
            memory_key=memory_key,
            kind=head.kind,
            status=MemoryStatus.TOMBSTONE,
            revision=head.revision + 1,
            content="",
            confidence=0.0,
            importance=0.0,
            source_refs=source_refs,
            metadata={},
            parent_ref=head.memory_ref,
            content_hash=content_hash,
            actor_id=access.actor_id,
            agent_run_id=access.agent_run_id,
            task_id=access.task_id,
            created_at=self.clock(),
        )
        return await self.store.append(record, expected_parent_ref=head.memory_ref)

    async def get_head(
        self,
        *,
        scope: MemoryScope,
        memory_key: str,
        access: MemoryAccessContext,
    ) -> MemoryRecord | None:
        resolved = scope.resolved(
            organization_id=access.organization_id,
            project_id=access.project_id,
        )
        self._authorize(resolved, access.read_scopes, "MEMORY_READ_DENIED")
        record = await self.store.get_head(
            organization_id=access.organization_id,
            project_id=_storage_project_id(resolved, access.project_id),
            scope_key=resolved.permission_key,
            memory_key=memory_key,
        )
        if (
            record is None
            or record.status is MemoryStatus.TOMBSTONE
            or _expired(record, self.clock())
        ):
            return None
        return record

    async def search(
        self,
        request: MemorySearchRequest,
        *,
        access: MemoryAccessContext,
    ) -> tuple[MemoryHit, ...]:
        requested = tuple(
            scope
            for scope in request.scopes
            if permission_allows(access.read_scopes, scope)
        )
        if not requested:
            return ()
        heads = await self.store.list_heads(
            organization_id=access.organization_id,
            project_id=access.project_id,
        )
        now = self.clock()
        hits: list[MemoryHit] = []
        for record in heads:
            if record.status is MemoryStatus.TOMBSTONE or _expired(record, now):
                continue
            if request.kinds and record.kind not in request.kinds:
                continue
            if not any(
                _scope_query_matches(scope, record.scope.permission_key)
                for scope in requested
            ):
                continue
            lexical = _lexical_score(request.query, record.content, record.memory_key)
            if request.query and lexical == 0:
                continue
            age_days = max(0.0, (now - record.created_at).total_seconds() / 86_400)
            recency = 1.0 / (1.0 + age_days / 30.0)
            hits.append(MemoryHit(record, lexical, recency))
        hits.sort(
            key=lambda hit: (
                hit.rank_score,
                hit.record.revision,
                hit.record.memory_ref,
            ),
            reverse=True,
        )
        return tuple(hits[: request.limit])

    @staticmethod
    def _authorize(scope: MemoryScope, granted: tuple[str, ...], code: str) -> None:
        if not permission_allows(granted, scope.permission_key):
            raise MemoryPermissionError(code)


def _storage_project_id(scope: MemoryScope, project_id):
    if scope.kind in {MemoryScopeKind.ORGANIZATION, MemoryScopeKind.USER}:
        return None
    return project_id


def _same_request(record, request, scope, project_id) -> bool:
    if record.project_id != project_id or record.scope != scope:
        return False
    if record.memory_key != request.memory_key or record.kind != request.kind:
        return False
    if record.status is not MemoryStatus.ACTIVE:
        return False
    return (
        record.content == request.content
        and record.confidence == float(request.confidence)
        and record.importance == float(request.importance)
        and record.source_refs == request.source_refs
        and dict(record.metadata) == dict(request.metadata)
        and record.expires_at == request.expires_at
    )


def _expired(record: MemoryRecord, now: datetime) -> bool:
    return record.expires_at is not None and record.expires_at <= now


def _scope_query_matches(query_scope: str, record_scope: str) -> bool:
    if ":" in query_scope:
        return query_scope == record_scope
    return record_scope == query_scope or record_scope.startswith(f"{query_scope}:")


def _lexical_score(query: str, content: str, key: str) -> float:
    if not query:
        return 0.5
    q = {token.lower() for token in _TOKEN.findall(query)}
    if not q:
        return 0.5
    d = {token.lower() for token in _TOKEN.findall(f"{key} {content}")}
    if not d:
        return 0.0
    overlap = len(q & d)
    return min(1.0, overlap / max(1, len(q)))
