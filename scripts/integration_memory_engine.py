from __future__ import annotations

import asyncio
import hashlib
import os
from contextlib import asynccontextmanager
from uuid import UUID, uuid5

import asyncpg

from lumi_agent_runtime.memory_engine import (
    MemoryAccessContext,
    MemoryActorType,
    MemoryCandidate,
    MemoryCandidateOutcome,
    MemoryKind,
    MemoryScope,
    MemorySearchQuery,
    MemorySourceRef,
    PostgresMemoryRepository,
    TransactionalMemoryEngineService,
)

ORG_ID = UUID("01900000-0000-7000-8000-000000000001")
PROJECT_ID = UUID("01900000-0000-7000-8000-000000000006")
PREFIX = "node35."


def _dsn(name: str) -> str:
    return os.environ[name].replace("postgresql+asyncpg://", "postgresql://", 1)


@asynccontextmanager
async def runtime_connection():
    connection = await asyncpg.connect(_dsn("DATABASE_URL"))
    try:
        yield connection
    finally:
        await connection.close()


def source(name: str) -> MemorySourceRef:
    return MemorySourceRef(
        source_type="node35-integration",
        source_id=name,
        version="1",
        content_hash=hashlib.sha256(name.encode()).hexdigest(),
    )


def access(
    *,
    actor_type: MemoryActorType = MemoryActorType.AGENT,
) -> MemoryAccessContext:
    return MemoryAccessContext(
        organization_id=ORG_ID,
        actor_type=actor_type,
        actor_id=(
            "node35-agent"
            if actor_type == MemoryActorType.AGENT
            else "node35-system"
        ),
        project_id=PROJECT_ID,
        agent_key="creative-director",
        session_id="node35-session",
    )


def candidate(
    name: str,
    key: str,
    summary: str,
    *,
    explicit: bool = False,
    embedding: tuple[float, ...] | None = None,
) -> MemoryCandidate:
    return MemoryCandidate(
        candidate_id=uuid5(PROJECT_ID, f"node35:{name}"),
        organization_id=ORG_ID,
        scope_type=MemoryScope.PROJECT,
        scope_id=str(PROJECT_ID),
        kind=MemoryKind.FACT,
        semantic_key=f"{PREFIX}{key}",
        content_structured={"value": summary},
        summary=summary,
        source_refs=(source(name),),
        confidence=0.8,
        created_by_type=MemoryActorType.AGENT,
        created_by_id="node35-agent",
        explicit_remember=explicit,
        embedding=embedding,
        embedding_model=(
            "node35-test-embedding" if embedding is not None else None
        ),
        embedding_version="1" if embedding is not None else None,
    )


async def cleanup(admin: asyncpg.Connection) -> None:
    await admin.execute(
        "DELETE FROM memory_candidates "
        "WHERE organization_id=$1 AND semantic_key LIKE $2",
        ORG_ID,
        f"{PREFIX}%",
    )
    await admin.execute(
        "UPDATE memory_records SET supersedes_id=NULL "
        "WHERE organization_id=$1 AND semantic_key LIKE $2",
        ORG_ID,
        f"{PREFIX}%",
    )
    await admin.execute(
        "DELETE FROM memory_records "
        "WHERE organization_id=$1 AND semantic_key LIKE $2",
        ORG_ID,
        f"{PREFIX}%",
    )


async def main_async() -> None:
    admin = await asyncpg.connect(_dsn("MIGRATION_DATABASE_URL"))
    service = TransactionalMemoryEngineService(
        PostgresMemoryRepository(runtime_connection)
    )
    try:
        assert await admin.fetchval(
            "SELECT count(*) FROM organizations WHERE id=$1",
            ORG_ID,
        ) == 1
        assert await admin.fetchval(
            "SELECT count(*) FROM projects WHERE id=$1",
            PROJECT_ID,
        ) == 1
        await cleanup(admin)

        same_a = candidate(
            "race-a",
            "race",
            "Prefer restrained studio lighting",
            explicit=True,
        )
        same_b = candidate(
            "race-b",
            "race",
            "Prefer restrained studio lighting",
            explicit=True,
        )
        race = await asyncio.gather(
            service.remember(same_a, access=access()),
            service.remember(same_b, access=access()),
        )
        assert {item.outcome for item in race} == {
            MemoryCandidateOutcome.WRITE,
            MemoryCandidateOutcome.DEDUPLICATE_CONFIRM,
        }
        active_race = await admin.fetch(
            """
            SELECT id,status,version FROM memory_records
            WHERE organization_id=$1 AND scope_type='PROJECT' AND scope_id=$2
              AND semantic_key=$3 AND status='ACTIVE'
            """,
            ORG_ID,
            str(PROJECT_ID),
            f"{PREFIX}race",
        )
        assert len(active_race) == 1
        assert int(active_race[0]["version"]) >= 2

        initial = await service.remember(
            candidate("palette-old", "palette", "Use cool gray"),
            access=access(),
        )
        conflict = await service.remember(
            candidate("palette-conflict", "palette", "Use warm gray"),
            access=access(),
        )
        assert conflict.outcome == MemoryCandidateOutcome.REQUIRE_CONFIRMATION
        replacement = await service.remember(
            candidate(
                "palette-new",
                "palette",
                "Use warm gray",
                explicit=True,
            ),
            access=access(),
        )
        assert replacement.outcome == MemoryCandidateOutcome.WRITE
        assert replacement.record is not None
        assert initial.record is not None
        assert replacement.record.supersedes_id == initial.record.memory_id
        old_status = await admin.fetchval(
            "SELECT status FROM memory_records WHERE id=$1",
            initial.record.memory_id,
        )
        assert old_status == "SUPERSEDED"

        results = await service.search(
            MemorySearchQuery(
                access=access(),
                text="warm gray",
                limit=10,
                scope_types=(MemoryScope.PROJECT,),
            )
        )
        assert any(
            row.record.semantic_key == f"{PREFIX}palette" for row in results
        )
        assert all(row.record.organization_id == ORG_ID for row in results)
        assert all(row.record.scope_id == str(PROJECT_ID) for row in results)

        deletable = await service.remember(
            candidate(
                "delete-me",
                "delete",
                "Temporary approved note",
                explicit=True,
            ),
            access=access(),
        )
        assert deletable.record is not None
        deleted = await service.delete(
            deletable.record.memory_id,
            access=access(actor_type=MemoryActorType.SYSTEM),
        )
        assert deleted.status.value == "DELETED"

        vector = await service.remember(
            candidate(
                "vector",
                "vector",
                "Vector-backed memory",
                explicit=True,
                embedding=(1.0, 0.0, 0.0),
            ),
            access=access(),
        )
        assert vector.record is not None
        vector_text = await admin.fetchval(
            "SELECT embedding::text FROM memory_records WHERE id=$1",
            vector.record.memory_id,
        )
        assert vector_text is not None and vector_text.startswith("[")
        assert await admin.fetchval(
            "SELECT embedding_dimensions FROM memory_records WHERE id=$1",
            vector.record.memory_id,
        ) == 3

        candidate_outcomes = {
            row["outcome"]
            for row in await admin.fetch(
                "SELECT outcome FROM memory_candidates "
                "WHERE organization_id=$1 AND semantic_key LIKE $2",
                ORG_ID,
                f"{PREFIX}%",
            )
        }
        assert {
            "WRITE",
            "DEDUPLICATE_CONFIRM",
            "REQUIRE_CONFIRMATION",
        } <= candidate_outcomes

        runtime = await asyncpg.connect(_dsn("DATABASE_URL"))
        try:
            try:
                await runtime.execute(
                    "DELETE FROM memory_records WHERE id=$1",
                    vector.record.memory_id,
                )
            except asyncpg.InsufficientPrivilegeError:
                pass
            else:
                raise AssertionError(
                    "lumi_app unexpectedly has DELETE on memory_records"
                )
        finally:
            await runtime.close()
    finally:
        await cleanup(admin)
        await admin.close()


def main() -> int:
    asyncio.run(main_async())
    print("NODE-35 PostgreSQL Memory Engine integration: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
