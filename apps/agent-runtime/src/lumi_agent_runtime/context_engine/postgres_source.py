from __future__ import annotations

import hashlib
import json
import math
from contextlib import AbstractAsyncContextManager
from dataclasses import replace
from typing import Any, Callable, Protocol
from uuid import UUID

from .contracts import (
    ContextItem,
    ContextKind,
    ContextLayer,
    ContextRequest,
    ContextSourceRef,
    TrustLevel,
)
from .retrieval import RetrievalCandidate


class ContextReadConnection(Protocol):
    async def fetch(self, query: str, *args: object) -> list[Any]: ...
    async def fetchrow(self, query: str, *args: object) -> Any | None: ...


ConnectionFactory = Callable[[], AbstractAsyncContextManager[ContextReadConnection]]


class PostgresProjectContextSource:
    """Read-only durable Project/Brand/Task/Asset/Artifact context adapter.

    Query embeddings, when present, must be supplied by the caller through NODE-22;
    this adapter never invokes an embedding provider itself.
    """

    def __init__(
        self,
        connection_factory: ConnectionFactory,
        *,
        system_items: tuple[ContextItem, ...] = (),
        agent_items: tuple[ContextItem, ...] = (),
    ) -> None:
        self.connection_factory = connection_factory
        self.system_items = system_items
        self.agent_items = agent_items

    async def load_system(self, request: ContextRequest) -> tuple[ContextItem, ...]:
        return self.system_items

    async def load_project(self, request: ContextRequest) -> tuple[ContextItem, ...]:
        async with self.connection_factory() as connection:
            summary = await connection.fetchrow(
                """
                SELECT id, summary, source_digest, version, updated_at
                FROM project_summaries
                WHERE organization_id = $1 AND project_id = $2
                ORDER BY version DESC
                LIMIT 1
                """,
                request.organization_id,
                request.project_id,
            )
            brand_rows = await connection.fetch(
                """
                SELECT b.id AS brand_id, b.name AS brand_name,
                       b.description AS brand_description,
                       r.id AS rule_id, r.rule_type, r.rule_key, r.rule_json,
                       r.source, r.version
                FROM projects p
                JOIN brands b ON b.id = p.brand_id
                LEFT JOIN brand_rules r ON r.brand_id = b.id
                WHERE p.id = $1 AND p.organization_id = $2
                ORDER BY r.rule_type, r.rule_key
                """,
                request.project_id,
                request.organization_id,
            )
        items: list[ContextItem] = []
        if summary is not None:
            content = str(summary["summary"])
            version = str(summary["version"])
            items.append(
                _item(
                    item_id=f"project-summary:{summary['id']}",
                    layer=ContextLayer.L1_PROJECT,
                    kind=ContextKind.PROJECT_SUMMARY,
                    content=content,
                    source_type="project_summary",
                    source_id=str(summary["id"]),
                    version=version,
                    trust=TrustLevel.TRUSTED_PROJECT,
                    priority=900,
                    metadata={"source_digest": str(summary["source_digest"])},
                )
            )
        for row in brand_rows:
            if row["rule_id"] is None:
                continue
            content = json.dumps(
                {
                    "brand": row["brand_name"],
                    "rule_type": row["rule_type"],
                    "rule_key": row["rule_key"],
                    "rule": row["rule_json"],
                    "source": row["source"],
                },
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )
            items.append(
                _item(
                    item_id=f"brand-rule:{row['rule_id']}",
                    layer=ContextLayer.L1_PROJECT,
                    kind=ContextKind.BRAND_RULE,
                    content=content,
                    source_type="brand_rule",
                    source_id=str(row["rule_id"]),
                    version=str(row["version"]),
                    trust=TrustLevel.TRUSTED_PROJECT,
                    priority=1000,
                )
            )
        return tuple(items)

    async def load_agent(self, request: ContextRequest) -> tuple[ContextItem, ...]:
        return tuple(
            item
            for item in self.agent_items
            if item.metadata.get("agent_ref") in (None, request.agent_ref)
        )

    async def load_task(self, request: ContextRequest) -> tuple[ContextItem, ...]:
        if request.task_id is None:
            return ()
        async with self.connection_factory() as connection:
            task = await connection.fetchrow(
                """
                SELECT id, task_key, recipe_step_id, type, owner_key, status,
                       input_json, output_json, metadata_json, state_version,
                       wait_reason, external_ref
                FROM tasks
                WHERE id = $1 AND organization_id = $2 AND project_id = $3
                """,
                request.task_id,
                request.organization_id,
                request.project_id,
            )
            dependencies = await connection.fetch(
                """
                SELECT d.depends_on_task_id AS id, t.task_key, t.status,
                       t.output_json, t.state_version
                FROM task_dependencies d
                JOIN tasks t ON t.id = d.depends_on_task_id
                WHERE d.task_id = $1 AND d.organization_id = $2
                ORDER BY t.created_at, t.task_key
                """,
                request.task_id,
                request.organization_id,
            )
        if task is None:
            return ()
        content = json.dumps(
            {
                "task_key": task["task_key"],
                "recipe_step_id": task["recipe_step_id"],
                "type": task["type"],
                "owner": task["owner_key"],
                "status": task["status"],
                "input": task["input_json"],
                "wait_reason": task["wait_reason"],
                "external_ref": task["external_ref"],
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        items: list[ContextItem] = [
            _item(
                item_id=f"task:{task['id']}",
                layer=ContextLayer.L3_TASK,
                kind=ContextKind.TASK_INPUT,
                content=content,
                source_type="task",
                source_id=str(task["id"]),
                version=str(task["state_version"]),
                trust=TrustLevel.TRUSTED_PROJECT,
                priority=1000,
            )
        ]
        for row in dependencies:
            if not row["output_json"]:
                continue
            items.append(
                _item(
                    item_id=f"task-output:{row['id']}",
                    layer=ContextLayer.L3_TASK,
                    kind=ContextKind.TASK_OUTPUT,
                    content=json.dumps(
                        {
                            "task_key": row["task_key"],
                            "status": row["status"],
                            "output": row["output_json"],
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str,
                    ),
                    source_type="task",
                    source_id=str(row["id"]),
                    version=str(row["state_version"]),
                    trust=TrustLevel.TRUSTED_PROJECT,
                    priority=800,
                )
            )
        return tuple(items)

    async def search(self, request: ContextRequest) -> tuple[RetrievalCandidate, ...]:
        query = request.query.strip()
        async with self.connection_factory() as connection:
            lexical_assets = await connection.fetch(
                """
                SELECT a.id, a.version, a.kind, a.original_filename,
                       m.title, m.description, m.tags_json, m.source
                FROM assets a
                LEFT JOIN asset_metadata m ON m.asset_id = a.id
                WHERE a.organization_id = $1 AND a.project_id = $2
                  AND a.status NOT IN ('deleted','quarantined')
                  AND (
                    $3 = '' OR
                    coalesce(m.title,'') ILIKE '%' || $3 || '%' OR
                    coalesce(m.description,'') ILIKE '%' || $3 || '%' OR
                    coalesce(a.original_filename,'') ILIKE '%' || $3 || '%'
                  )
                ORDER BY a.updated_at DESC
                LIMIT $4
                """,
                request.organization_id,
                request.project_id,
                query,
                request.retrieval_limit,
            )
            artifact_rows = await connection.fetch(
                """
                SELECT id, to_jsonb(a) AS record
                FROM artifacts a
                WHERE a.organization_id = $1 AND a.project_id = $2
                  AND ($3 = '' OR to_jsonb(a)::text ILIKE '%' || $3 || '%')
                ORDER BY a.created_at DESC
                LIMIT $4
                """,
                request.organization_id,
                request.project_id,
                query,
                request.retrieval_limit,
            )
            semantic_assets: list[Any] = []
            vector = _query_vector(request.metadata.get("query_embedding"))
            if vector is not None:
                semantic_assets = await connection.fetch(
                    """
                    SELECT a.id, a.version, a.kind, a.original_filename,
                           m.title, m.description, m.tags_json, m.source,
                           1 - (e.embedding <=> $3::vector) AS semantic_score
                    FROM asset_embeddings e
                    JOIN assets a ON a.id = e.asset_id
                    LEFT JOIN asset_metadata m ON m.asset_id = a.id
                    WHERE a.organization_id = $1 AND a.project_id = $2
                      AND a.status NOT IN ('deleted','quarantined')
                      AND e.dims = $4
                    ORDER BY e.embedding <=> $3::vector
                    LIMIT $5
                    """,
                    request.organization_id,
                    request.project_id,
                    _vector_literal(vector),
                    len(vector),
                    request.retrieval_limit,
                )

        candidates: dict[tuple[str, str, str], RetrievalCandidate] = {}
        for row in lexical_assets:
            item = _asset_item(row)
            candidate = RetrievalCandidate(
                item=item,
                organization_id=str(request.organization_id),
                project_id=str(request.project_id),
                lexical_score=_lexical_score(query, item.content),
                authority_score=0.75,
                recency_score=0.5,
            )
            candidates[_candidate_key(item)] = candidate
        for row in semantic_assets:
            item = _asset_item(row)
            key = _candidate_key(item)
            previous = candidates.get(key)
            semantic = max(0.0, min(1.0, float(row["semantic_score"] or 0)))
            candidates[key] = RetrievalCandidate(
                item=item,
                organization_id=str(request.organization_id),
                project_id=str(request.project_id),
                lexical_score=previous.lexical_score if previous else _lexical_score(query, item.content),
                semantic_score=semantic,
                authority_score=0.75,
                recency_score=0.5,
            )
        for row in artifact_rows:
            record = dict(row["record"])
            version = str(record.get("version") or record.get("updated_at") or record.get("created_at") or "1")
            item = _item(
                item_id=f"artifact:{row['id']}",
                layer=ContextLayer.L4_RETRIEVED,
                kind=ContextKind.ARTIFACT,
                content=json.dumps(record, ensure_ascii=False, sort_keys=True, default=str),
                source_type="artifact",
                source_id=str(row["id"]),
                version=version,
                trust=TrustLevel.TRUSTED_PROJECT,
                priority=700,
            )
            candidates[_candidate_key(item)] = RetrievalCandidate(
                item=item,
                organization_id=str(request.organization_id),
                project_id=str(request.project_id),
                lexical_score=_lexical_score(query, item.content),
                authority_score=0.85,
                recency_score=0.65,
            )
        return tuple(candidates.values())


def _asset_item(row: Any) -> ContextItem:
    content = json.dumps(
        {
            "kind": row["kind"],
            "filename": row["original_filename"],
            "title": row["title"],
            "description": row["description"],
            "tags": row["tags_json"],
            "source": row["source"],
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return _item(
        item_id=f"asset:{row['id']}",
        layer=ContextLayer.L4_RETRIEVED,
        kind=ContextKind.ASSET,
        content=content,
        source_type="asset",
        source_id=str(row["id"]),
        version=str(row["version"]),
        trust=TrustLevel.UNTRUSTED_RETRIEVED,
        priority=650,
    )


def _item(
    *,
    item_id: str,
    layer: ContextLayer,
    kind: ContextKind,
    content: str,
    source_type: str,
    source_id: str,
    version: str,
    trust: TrustLevel,
    priority: int,
    metadata: dict[str, Any] | None = None,
) -> ContextItem:
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    return ContextItem(
        item_id=item_id,
        layer=layer,
        kind=kind,
        content=content,
        source=ContextSourceRef(
            source_type=source_type,
            source_id=source_id,
            version=version,
            content_hash=content_hash,
        ),
        trust=trust,
        priority=priority,
        metadata=metadata or {},
    )


def _candidate_key(item: ContextItem) -> tuple[str, str, str]:
    return (
        item.source.source_type,
        item.source.source_id,
        item.source.version,
    )


def _lexical_score(query: str, content: str) -> float:
    terms = {term.casefold() for term in query.split() if term.strip()}
    if not terms:
        return 0.25
    haystack = content.casefold()
    hits = sum(term in haystack for term in terms)
    return min(1.0, hits / len(terms))


def _query_vector(value: object) -> tuple[float, ...] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or not 1 <= len(value) <= 4096:
        raise ValueError("CONTEXT_QUERY_VECTOR_INVALID")
    vector = tuple(float(item) for item in value)
    if any(not math.isfinite(item) for item in vector):
        raise ValueError("CONTEXT_QUERY_VECTOR_INVALID")
    return vector


def _vector_literal(vector: tuple[float, ...]) -> str:
    return "[" + ",".join(format(value, ".10g") for value in vector) + "]"
