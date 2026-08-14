from __future__ import annotations

import hashlib
import json
import math
from contextlib import AbstractAsyncContextManager
from typing import Any, Callable, Protocol

from .contracts import ContextItem, ContextKind, ContextLayer, ContextRequest, ContextSourceRef, TrustLevel
from .retrieval import RetrievalCandidate


class ContextReadConnection(Protocol):
    async def fetch(self, query: str, *args: object) -> list[Any]: ...
    async def fetchrow(self, query: str, *args: object) -> Any | None: ...


ConnectionFactory = Callable[[], AbstractAsyncContextManager[ContextReadConnection]]


class PostgresProjectContextSource:
    """Read-only adapter over canonical Project/Brand/Task/Asset/Artifact facts."""

    def __init__(self, connection_factory: ConnectionFactory, *, system_items=(), agent_items=()) -> None:
        self.connection_factory = connection_factory
        self.system_items = tuple(system_items)
        self.agent_items = tuple(agent_items)

    async def load_system(self, request: ContextRequest) -> tuple[ContextItem, ...]:
        del request
        return self.system_items

    async def load_project(self, request: ContextRequest) -> tuple[ContextItem, ...]:
        async with self.connection_factory() as connection:
            project = await connection.fetchrow(
                """
                SELECT id, brief_json, brief_version, settings_json, brand_id, version
                FROM projects
                WHERE id = $1 AND organization_id = $2 AND deleted_at IS NULL
                """,
                request.project_id,
                request.organization_id,
            )
            brand_rows: list[Any] = []
            if project is not None and project["brand_id"] is not None:
                brand_rows = await connection.fetch(
                    """
                    SELECT b.id AS brand_id, b.name AS brand_name,
                           b.profile_json, b.tone_json, b.version AS brand_version,
                           r.id AS rule_id, r.rule_type, r.severity,
                           r.rule_json, r.version AS rule_version
                    FROM brands b
                    LEFT JOIN brand_rules r ON r.brand_id = b.id AND r.organization_id = b.organization_id
                    WHERE b.id = $1 AND b.organization_id = $2
                    ORDER BY r.rule_type, r.id
                    """,
                    project["brand_id"],
                    request.organization_id,
                )
        if project is None:
            return ()
        items = [
            _item(
                item_id=f"project-brief:{project['id']}",
                layer=ContextLayer.L1_PROJECT,
                kind=ContextKind.PROJECT_SUMMARY,
                content=json.dumps(
                    {"brief": project["brief_json"], "settings": project["settings_json"]},
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                ),
                source_type="project_brief",
                source_id=str(project["id"]),
                version=str(project["brief_version"]),
                trust=TrustLevel.TRUSTED_PROJECT,
                priority=900,
            )
        ]
        seen_brand_profile = False
        for row in brand_rows:
            if not seen_brand_profile:
                items.append(
                    _item(
                        item_id=f"brand-profile:{row['brand_id']}",
                        layer=ContextLayer.L1_PROJECT,
                        kind=ContextKind.BRAND_RULE,
                        content=json.dumps(
                            {"name": row["brand_name"], "profile": row["profile_json"], "tone": row["tone_json"]},
                            ensure_ascii=False,
                            sort_keys=True,
                            default=str,
                        ),
                        source_type="brand",
                        source_id=str(row["brand_id"]),
                        version=str(row["brand_version"]),
                        trust=TrustLevel.TRUSTED_PROJECT,
                        priority=950,
                    )
                )
                seen_brand_profile = True
            if row["rule_id"] is not None:
                items.append(
                    _item(
                        item_id=f"brand-rule:{row['rule_id']}",
                        layer=ContextLayer.L1_PROJECT,
                        kind=ContextKind.BRAND_RULE,
                        content=json.dumps(
                            {"rule_type": row["rule_type"], "severity": row["severity"], "rule": row["rule_json"]},
                            ensure_ascii=False,
                            sort_keys=True,
                            default=str,
                        ),
                        source_type="brand_rule",
                        source_id=str(row["rule_id"]),
                        version=str(row["rule_version"]),
                        trust=TrustLevel.TRUSTED_PROJECT,
                        priority=1000,
                    )
                )
        return tuple(items)

    async def load_agent(self, request: ContextRequest) -> tuple[ContextItem, ...]:
        return tuple(item for item in self.agent_items if item.metadata.get("agent_ref") in (None, request.agent_ref))

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
            deps = await connection.fetch(
                """
                SELECT t.id, t.task_key, t.status, t.output_json, t.state_version
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
        items = [
            _item(
                item_id=f"task:{task['id']}",
                layer=ContextLayer.L3_TASK,
                kind=ContextKind.TASK_INPUT,
                content=json.dumps(
                    {"task_key": task["task_key"], "recipe_step_id": task["recipe_step_id"], "type": task["type"], "owner": task["owner_key"], "status": task["status"], "input": task["input_json"], "wait_reason": task["wait_reason"], "external_ref": task["external_ref"]},
                    ensure_ascii=False, sort_keys=True, default=str,
                ),
                source_type="task", source_id=str(task["id"]), version=str(task["state_version"]),
                trust=TrustLevel.TRUSTED_PROJECT, priority=1000,
            )
        ]
        for row in deps:
            if row["output_json"]:
                items.append(
                    _item(
                        item_id=f"task-output:{row['id']}", layer=ContextLayer.L3_TASK, kind=ContextKind.TASK_OUTPUT,
                        content=json.dumps({"task_key": row["task_key"], "status": row["status"], "output": row["output_json"]}, ensure_ascii=False, sort_keys=True, default=str),
                        source_type="task", source_id=str(row["id"]), version=str(row["state_version"]), trust=TrustLevel.TRUSTED_PROJECT, priority=800,
                    )
                )
        return tuple(items)

    async def search(self, request: ContextRequest) -> tuple[RetrievalCandidate, ...]:
        query = request.query.strip()
        async with self.connection_factory() as connection:
            assets = await connection.fetch(
                """
                SELECT a.id, a.version, a.kind, a.original_name, a.metadata_json,
                       am.namespace, am.data_json
                FROM assets a
                LEFT JOIN asset_metadata am ON am.asset_id = a.id AND am.organization_id = a.organization_id
                WHERE a.organization_id = $1 AND a.project_id = $2
                  AND a.deleted_at IS NULL AND a.status = 'ready'
                  AND ($3 = '' OR coalesce(a.original_name,'') ILIKE '%' || $3 || '%'
                       OR a.metadata_json::text ILIKE '%' || $3 || '%'
                       OR coalesce(am.data_json::text,'') ILIKE '%' || $3 || '%')
                ORDER BY a.updated_at DESC
                LIMIT $4
                """,
                request.organization_id, request.project_id, query, request.retrieval_limit,
            )
            artifacts = await connection.fetch(
                """
                SELECT id, kind, title, metadata_json, version, created_at
                FROM artifacts
                WHERE organization_id = $1 AND project_id = $2
                  AND ($3 = '' OR coalesce(title,'') ILIKE '%' || $3 || '%' OR metadata_json::text ILIKE '%' || $3 || '%')
                ORDER BY created_at DESC LIMIT $4
                """,
                request.organization_id, request.project_id, query, request.retrieval_limit,
            )
            semantic: list[Any] = []
            vector = _query_vector(request.metadata.get("query_embedding"))
            if vector is not None:
                semantic = await connection.fetch(
                    """
                    SELECT a.id, a.version, a.kind, a.original_name, a.metadata_json,
                           1 - (e.embedding <=> $3::vector) AS semantic_score
                    FROM asset_embeddings e
                    JOIN assets a ON a.id = e.asset_id AND a.organization_id = e.organization_id
                    WHERE a.organization_id = $1 AND a.project_id = $2
                      AND a.deleted_at IS NULL AND a.status = 'ready'
                      AND e.dimensions = $4
                    ORDER BY e.embedding <=> $3::vector LIMIT $5
                    """,
                    request.organization_id, request.project_id, _vector_literal(vector), len(vector), request.retrieval_limit,
                )
        candidates: dict[tuple[str, str, str], RetrievalCandidate] = {}
        for row in assets:
            item = _asset_item(row)
            candidates[_key(item)] = RetrievalCandidate(item=item, organization_id=str(request.organization_id), project_id=str(request.project_id), lexical_score=_lexical_score(query, item.content), authority_score=0.75, recency_score=0.5)
        for row in semantic:
            item = _asset_item(row)
            key = _key(item); previous = candidates.get(key)
            candidates[key] = RetrievalCandidate(item=item, organization_id=str(request.organization_id), project_id=str(request.project_id), lexical_score=previous.lexical_score if previous else _lexical_score(query, item.content), semantic_score=max(0.0, min(1.0, float(row["semantic_score"] or 0))), authority_score=0.75, recency_score=0.5)
        for row in artifacts:
            content = json.dumps({"kind": row["kind"], "title": row["title"], "metadata": row["metadata_json"]}, ensure_ascii=False, sort_keys=True, default=str)
            item = _item(item_id=f"artifact:{row['id']}", layer=ContextLayer.L4_RETRIEVED, kind=ContextKind.ARTIFACT, content=content, source_type="artifact", source_id=str(row["id"]), version=str(row["version"]), trust=TrustLevel.TRUSTED_PROJECT, priority=700)
            candidates[_key(item)] = RetrievalCandidate(item=item, organization_id=str(request.organization_id), project_id=str(request.project_id), lexical_score=_lexical_score(query, content), authority_score=0.85, recency_score=0.65)
        return tuple(candidates.values())


def _asset_item(row: Any) -> ContextItem:
    content = json.dumps({"kind": row["kind"], "original_name": row["original_name"], "metadata": row["metadata_json"], "namespace": row.get("namespace") if hasattr(row, "get") else None, "namespace_data": row.get("data_json") if hasattr(row, "get") else None}, ensure_ascii=False, sort_keys=True, default=str)
    return _item(item_id=f"asset:{row['id']}", layer=ContextLayer.L4_RETRIEVED, kind=ContextKind.ASSET, content=content, source_type="asset", source_id=str(row["id"]), version=str(row["version"]), trust=TrustLevel.UNTRUSTED_RETRIEVED, priority=650)


def _item(*, item_id: str, layer: ContextLayer, kind: ContextKind, content: str, source_type: str, source_id: str, version: str, trust: TrustLevel, priority: int, metadata: dict[str, Any] | None = None) -> ContextItem:
    return ContextItem(item_id=item_id, layer=layer, kind=kind, content=content, source=ContextSourceRef(source_type=source_type, source_id=source_id, version=version, content_hash=hashlib.sha256(content.encode()).hexdigest()), trust=trust, priority=priority, metadata=metadata or {})


def _key(item: ContextItem) -> tuple[str, str, str]:
    return item.source.source_type, item.source.source_id, item.source.version


def _lexical_score(query: str, content: str) -> float:
    terms = {x.casefold() for x in query.split() if x.strip()}
    if not terms: return 0.25
    haystack = content.casefold(); return min(1.0, sum(term in haystack for term in terms) / len(terms))


def _query_vector(value: object) -> tuple[float, ...] | None:
    if value is None: return None
    if not isinstance(value, (list, tuple)) or not 1 <= len(value) <= 4096: raise ValueError("CONTEXT_QUERY_VECTOR_INVALID")
    vector = tuple(float(x) for x in value)
    if any(not math.isfinite(x) for x in vector): raise ValueError("CONTEXT_QUERY_VECTOR_INVALID")
    return vector


def _vector_literal(vector: tuple[float, ...]) -> str:
    return "[" + ",".join(format(x, ".10g") for x in vector) + "]"
