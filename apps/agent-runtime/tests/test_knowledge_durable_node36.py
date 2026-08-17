from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest

from lumi_agent_runtime.knowledge_engine import (
    DeterministicEmbedding,
    GitWorkspaceKnowledgeStore,
    KnowledgeAccessContext,
    KnowledgeEngine,
    KnowledgeExtractionResult,
    KnowledgeIngestionService,
    KnowledgeSearchRequest,
    KnowledgeSourceInput,
    KnowledgeSourceType,
    SourceSection,
)

ORG = UUID("018f4b18-4b9e-7c2b-8a7b-11f5257d3001")
PROJECT = UUID("018f4b18-4b9e-7c2b-8a7b-11f5257d3002")
NOW = datetime(2026, 8, 17, 7, 0, tzinfo=timezone.utc)


def access() -> KnowledgeAccessContext:
    return KnowledgeAccessContext(
        organization_id=ORG,
        project_id=PROJECT,
        actor_id="node36-durable-test",
        read_scopes=("project",),
    )


class Extractor:
    def __init__(self, *, native: bool) -> None:
        self.native = native
        self.native_calls = 0
        self.ocr_calls = 0

    async def extract_native(self, source, *, access):
        del source, access
        self.native_calls += 1
        if not self.native:
            return None
        return KnowledgeExtractionResult(
            sections=(SourceSection(page=3, section="Facts", text="Alpha price is 42."),),
            parser_version="native-v1",
            language="en",
            used_ocr=False,
        )

    async def extract_ocr(self, source, *, access):
        del source, access
        self.ocr_calls += 1
        return KnowledgeExtractionResult(
            sections=(SourceSection(page=4, section="OCR", text="Scanned fact is 77."),),
            parser_version="ocr-v1",
            language="en",
            used_ocr=True,
        )


def source() -> KnowledgeSourceInput:
    return KnowledgeSourceInput(
        source_type=KnowledgeSourceType.UPLOADED_DOCUMENT,
        source_ref="asset://durable-guide",
        title="Durable Guide",
        organization_id=ORG,
        project_id=PROJECT,
        permission_scope="project",
        observed_at=NOW,
        source_updated_at=NOW,
    )


@pytest.mark.asyncio
async def test_native_extraction_precedes_ocr(tmp_path) -> None:
    extractor = Extractor(native=True)
    engine = KnowledgeEngine(store=GitWorkspaceKnowledgeStore(tmp_path))
    document = await KnowledgeIngestionService(engine, extractor=extractor).ingest(
        access(), source()
    )
    assert extractor.native_calls == 1
    assert extractor.ocr_calls == 0
    assert document.metadata["used_ocr"] is False


@pytest.mark.asyncio
async def test_ocr_is_fallback_only(tmp_path) -> None:
    extractor = Extractor(native=False)
    engine = KnowledgeEngine(store=GitWorkspaceKnowledgeStore(tmp_path))
    document = await KnowledgeIngestionService(engine, extractor=extractor).ingest(
        access(), source()
    )
    assert extractor.native_calls == 1
    assert extractor.ocr_calls == 1
    assert document.metadata["used_ocr"] is True
    hit = engine.search(
        access(),
        KnowledgeSearchRequest(query="scanned 77", permission_scopes=("project",)),
        now=NOW,
    ).hits[0]
    assert hit.citation.page == 4


@pytest.mark.asyncio
async def test_workspace_restart_preserves_active_index_and_citation(tmp_path) -> None:
    engine = KnowledgeEngine(store=GitWorkspaceKnowledgeStore(tmp_path))
    first = await KnowledgeIngestionService(engine, extractor=Extractor(native=True)).ingest(
        access(), source()
    )
    before = engine.search(
        access(),
        KnowledgeSearchRequest(query="Alpha price", permission_scopes=("project",)),
        now=NOW,
    ).hits[0]

    restarted = KnowledgeEngine(store=GitWorkspaceKnowledgeStore(tmp_path))
    after = restarted.search(
        access(),
        KnowledgeSearchRequest(query="Alpha price", permission_scopes=("project",)),
        now=NOW,
    ).hits[0]
    assert after.document.document_id == first.document_id
    assert after.citation.page == before.citation.page == 3
    assert after.citation.content_hash == before.citation.content_hash


@pytest.mark.asyncio
async def test_reindex_keeps_old_version_and_moves_active_head(tmp_path) -> None:
    engine = KnowledgeEngine(store=GitWorkspaceKnowledgeStore(tmp_path))
    first = await KnowledgeIngestionService(engine, extractor=Extractor(native=True)).ingest(
        access(), source()
    )
    rebuilt = engine.reindex(
        access(),
        first.document_id,
        __import__("lumi_agent_runtime.knowledge_engine", fromlist=["KnowledgeIngestRequest"]).KnowledgeIngestRequest(
            source_type=KnowledgeSourceType.UPLOADED_DOCUMENT,
            source_ref=source().source_ref,
            title=source().title,
            parser_version="native-v1",
            language="en",
            permission_scope="project",
            sections=(SourceSection(page=3, section="Facts", text="Alpha price is 42."),),
            organization_id=ORG,
            project_id=PROJECT,
            observed_at=NOW,
            source_updated_at=NOW,
        ),
        embedder=DeterministicEmbedding(version="deterministic-96-v2", dimensions=96),
        now=NOW,
    )
    assert rebuilt.document_id != first.document_id
    assert len(engine.source_history(access(), first.document_id)) == 2
    active = engine.search(
        access(),
        KnowledgeSearchRequest(query="Alpha price", permission_scopes=("project",)),
        now=NOW,
    ).hits[0]
    assert active.document.document_id == rebuilt.document_id

    restarted = KnowledgeEngine(store=GitWorkspaceKnowledgeStore(tmp_path))
    active_after_restart = restarted.search(
        access(),
        KnowledgeSearchRequest(query="Alpha price", permission_scopes=("project",)),
        now=NOW,
    ).hits[0]
    assert active_after_restart.document.document_id == rebuilt.document_id

    restarted.rollback_index(access(), first.document_id)
    rolled_back = restarted.search(
        access(),
        KnowledgeSearchRequest(query="Alpha price", permission_scopes=("project",)),
        now=NOW,
    ).hits[0]
    assert rolled_back.document.document_id == first.document_id


def test_delete_current_head_does_not_resurrect_old_version(tmp_path) -> None:
    store = GitWorkspaceKnowledgeStore(tmp_path)
    engine = KnowledgeEngine(store=store)
    from lumi_agent_runtime.knowledge_engine import KnowledgeIngestRequest

    base = KnowledgeIngestRequest(
        source_type=KnowledgeSourceType.UPLOADED_DOCUMENT,
        source_ref="asset://delete-head",
        title="Delete Head",
        parser_version="native-v1",
        language="en",
        permission_scope="project",
        sections=(SourceSection(text="Deletion fact 11"),),
        organization_id=ORG,
        project_id=PROJECT,
        observed_at=NOW,
        source_updated_at=NOW,
    )
    first = engine.ingest(access(), base, now=NOW)
    second = engine.reindex(
        access(),
        first.document_id,
        base,
        embedder=DeterministicEmbedding(version="deterministic-96-v2", dimensions=96),
        now=NOW,
    )
    engine.delete_document(access(), second.document_id)
    assert engine.search(
        access(),
        KnowledgeSearchRequest(query="Deletion fact", permission_scopes=("project",)),
        now=NOW,
    ).hits == ()
