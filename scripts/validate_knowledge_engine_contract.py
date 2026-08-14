from __future__ import annotations

import ast
from pathlib import Path

from lumi_agent_runtime.knowledge_engine import (
    KnowledgePermissionScope,
    KnowledgeSourceType,
    KnowledgeStatus,
    KnowledgeTrust,
)

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "apps/agent-runtime/src/lumi_agent_runtime/knowledge_engine"
REQUIRED = {
    "__init__.py",
    "chunking.py",
    "context_source.py",
    "contracts.py",
    "extraction.py",
    "indexer.py",
    "ingestion.py",
    "postgres_repository.py",
    "repository.py",
    "retrieval.py",
    "service.py",
}
FORBIDDEN_IMPORTS = {
    "asyncpg",
    "sqlalchemy",
    "psycopg",
    "requests",
    "httpx",
    "subprocess",
    "docker",
    "openai",
    "anthropic",
    "google",
}


def require(path: str, *markers: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    for marker in markers:
        if marker not in text:
            raise SystemExit(f"{path}: missing NODE-36 marker: {marker}")
    return text


def main() -> int:
    missing = sorted(name for name in REQUIRED if not (PACKAGE / name).is_file())
    if missing:
        raise SystemExit(f"NODE-36 Knowledge modules missing: {missing}")

    if {item.value for item in KnowledgeSourceType} != {
        "ASSET",
        "URL",
        "TEXT",
        "ARTIFACT",
        "INTERNAL_DOCUMENT",
    }:
        raise SystemExit("NODE-36 source type vocabulary drifted")
    if {item.value for item in KnowledgePermissionScope} != {
        "PROJECT",
        "ORGANIZATION",
    }:
        raise SystemExit("NODE-36 permission scope vocabulary drifted")
    required_status = {
        "PENDING",
        "EXTRACTING",
        "CHUNKING",
        "EMBEDDING",
        "READY",
        "FAILED",
        "STALE",
        "SUPERSEDED",
        "DELETED",
    }
    if {item.value for item in KnowledgeStatus} != required_status:
        raise SystemExit("NODE-36 ingestion state vocabulary drifted")
    if {item.value for item in KnowledgeTrust} != {
        "INTERNAL_DATA",
        "USER_CONTENT",
        "EXTERNAL_UNTRUSTED",
        "MODEL_GENERATED",
    }:
        raise SystemExit("NODE-36 trust vocabulary drifted")

    require(
        "apps/agent-runtime/src/lumi_agent_runtime/knowledge_engine/contracts.py",
        "KnowledgeIngestRequest",
        "KnowledgeSegment",
        "source_updated_at",
        "scope_key",
        "parser_version",
        "chunker_version",
        "index_version",
        "embedding_space_id",
        "expanded_queries",
        "require_fresh",
        "KNOWLEDGE_FRESHNESS_WINDOW_REQUIRED",
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/knowledge_engine/chunking.py",
        'locator["page"]',
        'locator["section"]',
        "segment_index",
        "scope_key",
        "index_version",
    )
    extraction = require(
        "apps/agent-runtime/src/lumi_agent_runtime/knowledge_engine/extraction.py",
        "extract_native",
        "extract_ocr",
        "extract_native_then_ocr",
        "used_ocr",
    )
    if extraction.index("extract_native(") > extraction.index("extract_ocr("):
        raise SystemExit("NODE-36 OCR is attempted before native extraction")

    ingestion = require(
        "apps/agent-runtime/src/lumi_agent_runtime/knowledge_engine/ingestion.py",
        "TransactionalKnowledgeIngestionService",
        "KnowledgeStatus.PENDING",
        "KnowledgeStatus.EXTRACTING",
        "extract_native_then_ocr",
        "KNOWLEDGE_EXTRACTION_FAILED",
        "KNOWLEDGE_INDEX_FINALIZE_FAILED",
        "ingest_config_hash",
    )
    ingest_body = ingestion.split("async def ingest", 1)[1].split(
        "async def _begin_extraction",
        1,
    )[0]
    if "self.repository.transaction()" in ingest_body:
        raise SystemExit("NODE-36 extraction is held inside a durable DB transaction")

    indexer = require(
        "apps/agent-runtime/src/lumi_agent_runtime/knowledge_engine/indexer.py",
        "acquire_source_lock",
        "request.scope_key",
        "KNOWLEDGE_INDEX_VERSION_CONFIGURATION_CONFLICT",
        "KNOWLEDGE_INGEST_CONFIGURATION_CONFLICT",
        "KnowledgeStatus.CHUNKING",
        "KnowledgeStatus.EMBEDDING",
        "KnowledgeStatus.READY",
        "KnowledgeStatus.SUPERSEDED",
        "KnowledgeEmbeddingPort",
        "embedding_space_id",
    )
    if "openai" in indexer.lower() or "anthropic" in indexer.lower():
        raise SystemExit("NODE-36 indexer bypasses Model Gateway boundary")

    retrieval = require(
        "apps/agent-runtime/src/lumi_agent_runtime/knowledge_engine/retrieval.py",
        "include_organization_scope",
        "search_ready_chunks",
        "query.expanded_queries",
        "query.require_fresh",
        "query_embedding_space_id",
        "candidate_limit",
        "_diversify",
        "score = min",
    )
    if retrieval.index("search_ready_chunks") > retrieval.index("score = min"):
        raise SystemExit("NODE-36 retrieval scores before scoped candidate retrieval")

    postgres = require(
        "apps/agent-runtime/src/lumi_agent_runtime/knowledge_engine/postgres_repository.py",
        "pg_advisory_xact_lock",
        "scope_key",
        "FOR UPDATE",
        "d.project_id=$2",
        "d.permission_scope='ORGANIZATION'",
        "websearch_to_tsquery",
        "c.search_tsv",
        "c.embedding <=> $4::vector",
        "c.embedding_space_id=$5",
        "ON CONFLICT (document_id, ordinal) DO UPDATE",
        "version=version+1",
        "_decode_vector",
    )
    for forbidden in FORBIDDEN_IMPORTS:
        if f"import {forbidden}" in postgres or f"from {forbidden}" in postgres:
            raise SystemExit(f"NODE-36 Postgres repository imports concrete SDK: {forbidden}")

    require(
        "apps/agent-runtime/src/lumi_agent_runtime/knowledge_engine/context_source.py",
        "ContextKind.KNOWLEDGE",
        '"instruction_authority": "none"',
        "_embedding_pair",
        "citation_source_id",
        "citation_source_hash",
        "knowledge_stale",
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/context_engine/contracts.py",
        'KNOWLEDGE = "KNOWLEDGE"',
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/knowledge_engine/service.py",
        "TransactionalKnowledgeService",
        "KnowledgeStatus.DELETED",
        "KnowledgeStatus.STALE",
        "knowledge.organization.write",
    )

    migration = require(
        "apps/api/alembic/versions/0017_knowledge_engine.py",
        'down_revision = "0016_memory_engine"',
        "CREATE TABLE knowledge_documents",
        "CREATE TABLE knowledge_chunks",
        "permission_scope",
        "scope_key",
        "scope_key='PROJECT:' || project_id::text",
        "parser_version",
        "chunker_version",
        "index_version",
        "embedding_space_id",
        "search_tsv tsvector GENERATED ALWAYS AS",
        "USING gin (search_tsv)",
        "REVOKE DELETE",
    )
    if "raw_chat" in migration or "conversation_history" in migration:
        raise SystemExit("NODE-36 schema incorrectly stores conversation history")
    require(
        "apps/api/src/lumi_api/persistence/models/knowledge.py",
        '__tablename__ = "knowledge_documents"',
        '__tablename__ = "knowledge_chunks"',
        "permission_scope",
        "scope_key",
        "index_version",
        "embedding_space_id",
        "Computed(\"to_tsvector('simple', text)\"",
        'postgresql_using="gin"',
    )
    require(
        "apps/api/src/lumi_api/persistence/models/__init__.py",
        "KnowledgeChunkModel",
        "KnowledgeDocumentModel",
    )
    require(
        "apps/agent-runtime/tests/test_knowledge_scope_identity.py",
        "same_source_can_exist_in_two_projects_without_cross_supersede",
    )
    require(
        "apps/agent-runtime/tests/test_knowledge_boundaries.py",
        "same_index_version_rejects_configuration_drift",
        "context_embedding_without_space_falls_back_to_lexical",
    )
    require(
        "scripts/integration_knowledge_engine.py",
        "TransactionalKnowledgeIngestionService",
        "asyncio.gather",
        '"SUPERSEDED"',
        'locator["page"] == 2',
        "InsufficientPrivilegeError",
        "embedding::text",
    )

    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".", 1)[0] for alias in node.names}
                if roots & FORBIDDEN_IMPORTS:
                    raise SystemExit(f"Knowledge Engine imports ambient authority: {path}")
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".", 1)[0] in FORBIDDEN_IMPORTS:
                    raise SystemExit(f"Knowledge Engine imports ambient authority: {path}")

    for path in PACKAGE.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "lumi_agent_runtime.memory_engine" in text:
            raise SystemExit(f"Knowledge Engine incorrectly depends on Memory Engine: {path}")

    print("NODE-36 Knowledge Engine static contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
