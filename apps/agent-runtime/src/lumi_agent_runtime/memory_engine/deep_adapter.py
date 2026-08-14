from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Iterable
from typing import Any, Awaitable
from uuid import UUID, uuid5

from langgraph.store.base import (
    BaseStore,
    GetOp,
    Item,
    ListNamespacesOp,
    Op,
    PutOp,
    Result,
    SearchItem,
    SearchOp,
)

from lumi_agent_runtime.deep_runtime.contracts import DeepAgentInvocationContext

from .contracts import (
    MemoryAccessContext,
    MemoryActorType,
    MemoryCandidate,
    MemoryKind,
    MemoryScope,
    MemorySearchQuery,
    MemorySourceRef,
)
from .service import MemoryEngineService, TransactionalMemoryEngineService

_VIRTUAL_NAMESPACE = ("memory",)
MemoryService = MemoryEngineService | TransactionalMemoryEngineService


class DeepAgentMemoryStore(BaseStore):
    """LangGraph BaseStore mapped to one server-selected LUMI memory scope."""

    supports_ttl = False

    def __init__(
        self,
        *,
        service: MemoryService,
        access: MemoryAccessContext,
        scope_type: MemoryScope,
        scope_id: str,
        source_ref: MemorySourceRef,
    ) -> None:
        super().__init__()
        self.service = service
        self.access = access
        self.scope_type = scope_type
        self.scope_id = scope_id
        self.source_ref = source_ref

    async def abatch(self, ops: Iterable[Op]) -> list[Result]:
        results: list[Result] = []
        for op in ops:
            if isinstance(op, GetOp):
                self._assert_namespace(op.namespace)
                results.append(await self._get(op.key))
            elif isinstance(op, PutOp):
                self._assert_namespace(op.namespace)
                if op.value is None:
                    await self._delete(op.key)
                else:
                    await self._put(op.key, dict(op.value))
                results.append(None)
            elif isinstance(op, SearchOp):
                self._assert_namespace_prefix(op.namespace_prefix)
                results.append(
                    await self._search(
                        op.query or "memory",
                        limit=op.limit,
                        offset=op.offset,
                    )
                )
            elif isinstance(op, ListNamespacesOp):
                results.append([_VIRTUAL_NAMESPACE])
            else:
                raise TypeError(
                    f"MEMORY_STORE_OPERATION_UNSUPPORTED:{type(op).__name__}"
                )
        return results

    def batch(self, ops: Iterable[Op]) -> list[Result]:
        return _run_sync(self.abatch(ops))

    async def _get(self, key: str) -> Item | None:
        rows = await self.service.search(
            MemorySearchQuery(
                access=self.access,
                text=key,
                limit=50,
                scope_types=(self.scope_type,),
            )
        )
        match = next(
            (
                row.record
                for row in rows
                if row.record.semantic_key == key
                and row.record.scope_id == self.scope_id
            ),
            None,
        )
        return _item(match) if match is not None else None

    async def _put(self, key: str, value: dict[str, Any]) -> None:
        kind = MemoryKind(
            str(value.get("kind", MemoryKind.WORKFLOW_LEARNING.value))
        )
        summary = str(value.get("summary") or value.get("content") or "").strip()
        if not summary:
            raise ValueError("MEMORY_STORE_SUMMARY_REQUIRED")
        structured = value.get("content_structured", value)
        if not isinstance(structured, dict):
            raise ValueError("MEMORY_STORE_VALUE_MUST_BE_OBJECT")
        explicit = bool(value.get("explicit_remember", False))
        confidence = float(value.get("confidence", 0.75))
        material = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        candidate_id = uuid5(
            self.access.organization_id,
            (
                f"deep-memory:{self.scope_type.value}:{self.scope_id}:{key}:"
                f"{hashlib.sha256(material.encode()).hexdigest()}"
            ),
        )
        candidate = MemoryCandidate(
            candidate_id=candidate_id,
            organization_id=self.access.organization_id,
            scope_type=self.scope_type,
            scope_id=self.scope_id,
            kind=kind,
            semantic_key=key,
            content_structured=structured,
            summary=summary,
            source_refs=(self.source_ref,),
            confidence=confidence,
            created_by_type=self.access.actor_type,
            created_by_id=self.access.actor_id,
            explicit_remember=explicit,
            metadata={"source": "deep-agent-store"},
        )
        decision = await self.service.remember(candidate, access=self.access)
        if decision.outcome.value in {
            "REJECT_SCOPE",
            "REJECT_SENSITIVE",
            "REQUIRE_CONFIRMATION",
            "BRAND_RULE_PROPOSAL",
        }:
            raise PermissionError(
                f"MEMORY_STORE_WRITE_NOT_ACTIVE:{decision.outcome.value}:"
                f"{decision.reason}"
            )

    async def _delete(self, key: str) -> None:
        item = await self._get(key)
        if item is None:
            return
        memory_id = item.value.get("memory_id")
        if not isinstance(memory_id, str):
            raise ValueError("MEMORY_STORE_ITEM_ID_INVALID")
        await self.service.delete(UUID(memory_id), access=self.access)

    async def _search(
        self,
        query: str,
        *,
        limit: int,
        offset: int,
    ) -> list[SearchItem]:
        rows = await self.service.search(
            MemorySearchQuery(
                access=self.access,
                text=query,
                limit=min(50, max(1, limit + offset)),
                scope_types=(self.scope_type,),
            )
        )
        scoped = [
            row for row in rows if row.record.scope_id == self.scope_id
        ][offset : offset + limit]
        return [
            SearchItem(
                namespace=_VIRTUAL_NAMESPACE,
                key=row.record.semantic_key,
                value=_value(row.record),
                created_at=row.record.created_at,
                updated_at=row.record.last_confirmed_at or row.record.created_at,
                score=row.score,
            )
            for row in scoped
        ]

    def _assert_namespace(self, namespace: tuple[str, ...]) -> None:
        if namespace != _VIRTUAL_NAMESPACE:
            raise PermissionError("MEMORY_STORE_NAMESPACE_DENIED")

    def _assert_namespace_prefix(self, namespace: tuple[str, ...]) -> None:
        if namespace not in {(), _VIRTUAL_NAMESPACE}:
            raise PermissionError("MEMORY_STORE_NAMESPACE_DENIED")


def deep_agent_project_memory_store(
    *,
    service: MemoryService,
    context: DeepAgentInvocationContext,
) -> DeepAgentMemoryStore:
    access = MemoryAccessContext(
        organization_id=context.organization_id,
        actor_type=MemoryActorType.AGENT,
        actor_id=context.actor_id,
        project_id=context.project_id,
        agent_key=context.root_agent,
        session_id=str(context.agent_run_id),
        granted_permissions=context.granted_permissions,
    )
    source_ref = MemorySourceRef(
        source_type="agent_run",
        source_id=str(context.agent_run_id),
        version="1",
        content_hash=hashlib.sha256(
            (
                f"{context.organization_id}:{context.project_id}:"
                f"{context.agent_run_id}:{context.root_agent}"
            ).encode()
        ).hexdigest(),
    )
    return DeepAgentMemoryStore(
        service=service,
        access=access,
        scope_type=MemoryScope.PROJECT,
        scope_id=str(context.project_id),
        source_ref=source_ref,
    )


def _item(record) -> Item:
    return Item(
        namespace=_VIRTUAL_NAMESPACE,
        key=record.semantic_key,
        value=_value(record),
        created_at=record.created_at,
        updated_at=record.last_confirmed_at or record.created_at,
    )


def _value(record) -> dict[str, Any]:
    return {
        "memory_id": str(record.memory_id),
        "kind": record.kind.value,
        "summary": record.summary,
        "content_structured": record.content_structured,
        "confidence": record.confidence,
        "version": record.version,
        "source_refs": [
            {
                "source_type": ref.source_type,
                "source_id": ref.source_id,
                "version": ref.version,
                "content_hash": ref.content_hash,
            }
            for ref in record.source_refs
        ],
    }


def _run_sync(awaitable: Awaitable[list[Result]]) -> list[Result]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    raise RuntimeError("MEMORY_STORE_SYNC_CALL_INSIDE_EVENT_LOOP_USE_ASYNC_GRAPH")
