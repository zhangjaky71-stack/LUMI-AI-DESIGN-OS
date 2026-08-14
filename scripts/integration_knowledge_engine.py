from __future__ import annotations

import asyncio
import hashlib
import os
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import asyncpg

from lumi_agent_runtime.knowledge_engine import (
    KnowledgeAccessContext,
    KnowledgeIndexRequest,
    KnowledgePermissionScope,
    KnowledgeSearchQuery,
    KnowledgeSegment,
    KnowledgeSourceRef,
    KnowledgeSourceType,
    KnowledgeStatus,
    KnowledgeTrust,
    PostgresKnowledgeRepository,
    TransactionalKnowledgeService,
)

ORG_ID = UUID("01900000-0000-7000-8000-000000000001")
PROJECT_ID = UUID("01900000-0000-7000-8000-000000000006")
PREFIX = "node36-knowledge-"


def _dsn(name: str) -> str:
    return os.environ[name].replace("postgresql+asyncpg://", "postgresql://", 1)


@asynccontextmanager
async def runtime_connection():
    connection = await asyncpg.connect(_dsn("DATABASE_URL"))
    try:
        yield connection
    finally:
        await connection.close()


class FixtureEmbedder:
    async def embed(self, chunks, *, embedding_space_id: str):
        return tuple(
            replace(
                chunk,
                embedding=(0.9, 0.1, 0.2),
                embedding_model="node36-fixture",
                embedding_version="1",
                embedding_space_id=embedding_space_id,
            )
            for chunk in chunks
        )


def source(version: str) -> KnowledgeSourceRef:
    identity = f"{PREFIX}asset:{version}"
    return KnowledgeSourceRef(
        source_type=KnowledgeSourceType.ASSET,
        source_id=f"{PREFIX}asset",
        version=version,
        content_hash=hashlib.sha256(identity.encode()).hexdigest(),
        title="NODE-36 Product Guide.pdf",
        uri=f"asset://{PREFIX}asset",
        observed_at=datetime(2026, 8, 14, tzinfo=UTC),
        source_updated_at=datetime(2026, 8, 14, tzinfo=UTC),
    )


def access() -> KnowledgeAccessContext:
    return KnowledgeAccessContext(
        organization_id=ORG_ID,
        project_id=PROJECT_ID,
        actor_id="node36-integration",
    )


def index_request(version: str, pricing: str) -> KnowledgeIndexRequest:
    segments = (
        KnowledgeSegment(
            "NODE-36 product overview and positioning.",
            page=1,
            section="Overview",
        ),
        KnowledgeSegment(
            f"Annual enterprise pricing is {pricing} per seat.",
            page=2,
            section="Pricing",
        ),
    )
    return KnowledgeIndexRequest(
        access=access(),
        source=source(version),
        trust=KnowledgeTrust.USER_CONTENT,
        normalized_text="\n".join(segment.text for segment in segments),
        project_id=PROJECT_ID,
        permission_scope=KnowledgePermissionScope.PROJECT,
        parser_version="pdf-native-v1",
        chunker_version="structure-window-v1",
        index_version=f"node36-index-{version}",
        embedding_space_id="node36-embedding-space-v1",
        chunk_size_tokens=100,
        chunk_overlap_tokens=10,
        segments=segments,
    )


async def main_async() -> None:
    migration = await asyncpg.connect(_dsn("MIGRATION_DATABASE_URL"))
    runtime = await asyncpg.connect(_dsn("DATABASE_URL"))
    repository = PostgresKnowledgeRepository(runtime_connection)
    service = TransactionalKnowledgeService(
        repository,
        embedder=FixtureEmbedder(),
    )
    try:
        assert await migration.fetchval(
            "SELECT count(*) FROM organizations WHERE id=$1",
            ORG_ID,
        ) == 1
        assert await migration.fetchval(
            "SELECT count(*) FROM projects WHERE id=$1",
            PROJECT_ID,
        ) == 1

        await _cleanup(migration)

        first_request = index_request("1", "120 dollars")
        first_a, first_b = await asyncio.gather(
            service.index(first_request),
            service.index(first_request),
        )
        assert first_a.document_id == first_b.document_id
        assert first_a.status == KnowledgeStatus.READY
        assert await migration.fetchval(
            """
            SELECT count(*) FROM knowledge_documents
            WHERE organization_id=$1 AND source_id=$2 AND status='READY'
            """,
            ORG_ID,
            f"{PREFIX}asset",
        ) == 1

        results = await service.search(
            KnowledgeSearchQuery(
                access=access(),
                text="annual enterprise pricing",
                query_embedding=(0.9, 0.1, 0.2),
                query_embedding_space_id="node36-embedding-space-v1",
            )
        )
        assert results
        assert results[0].citation.locator["page"] == 2
        assert results[0].citation.locator["section"] == "Pricing"
        assert results[0].citation.source_version == "1"
        assert results[0].semantic_score > 0.99

        second = await service.index(index_request("2", "150 dollars"))
        assert second.status == KnowledgeStatus.READY
        old_status = await migration.fetchval(
            "SELECT status FROM knowledge_documents WHERE id=$1",
            first_a.document_id,
        )
        assert old_status == "SUPERSEDED"
        assert await migration.fetchval(
            """
            SELECT count(*) FROM knowledge_documents
            WHERE organization_id=$1 AND source_id=$2 AND status='READY'
            """,
            ORG_ID,
            f"{PREFIX}asset",
        ) == 1

        latest = await service.search(
            KnowledgeSearchQuery(
                access=access(),
                text="150 dollars pricing",
            )
        )
        assert latest
        assert {item.citation.source_version for item in latest} == {"2"}

        deleted = await service.delete(second.document_id, access=access())
        assert deleted.status == KnowledgeStatus.DELETED
        after_delete = await service.search(
            KnowledgeSearchQuery(
                access=access(),
                text="150 dollars pricing",
            )
        )
        assert after_delete == ()

        vector_text = await migration.fetchval(
            """
            SELECT embedding::text
            FROM knowledge_chunks
            WHERE document_id=$1
            ORDER BY ordinal
            LIMIT 1
            """,
            second.document_id,
        )
        assert vector_text is not None and vector_text.startswith("[")

        try:
            async with runtime.transaction():
                await runtime.execute(
                    "DELETE FROM knowledge_documents WHERE id=$1",
                    second.document_id,
                )
        except asyncpg.InsufficientPrivilegeError:
            pass
        else:
            raise AssertionError("lumi_app unexpectedly has DELETE on Knowledge tables")
    finally:
        await _cleanup(migration)
        await runtime.close()
        await migration.close()


async def _cleanup(connection) -> None:
    ids = await connection.fetch(
        """
        SELECT id FROM knowledge_documents
        WHERE organization_id=$1 AND source_id LIKE $2
        """,
        ORG_ID,
        f"{PREFIX}%",
    )
    document_ids = [row["id"] for row in ids]
    if document_ids:
        await connection.execute(
            "DELETE FROM knowledge_chunks WHERE document_id = ANY($1::uuid[])",
            document_ids,
        )
        await connection.execute(
            "DELETE FROM knowledge_documents WHERE id = ANY($1::uuid[])",
            document_ids,
        )


def main() -> int:
    asyncio.run(main_async())
    print("NODE-36 PostgreSQL Knowledge Engine integration: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
