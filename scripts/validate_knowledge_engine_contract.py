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
        "KnowledgeSegment",
        "source_updated_at",
        "parser_version",
        "chunker_version",
        "index_version",
        "embedding_space_id",
        "expanded_queries",
        "require_fresh",
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/knowledge_engine/chunking.py",
        'locator["page"]',
        'locator["section"]',
        "segment_index",
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

    indexer = require(
        "apps/agent-runtime/src/lumi_agent_runtime/knowledge_engine/indexer.py",
        "acquire_source_lock",
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
        "list_ready_chunks",
        "query.expanded_queries",
        "query.require_fresh",
        "query_embedding_space_id",
        "_diversify",
        "score = min",
    )
    if retrieval.index("list_ready_chunks") > retrieval.index("score = min"):
        raise SystemExit("NODE-36 retrieval scores before scoped repository filtering")

    postgres = require(
        "apps/agent-runtime/src/lumi_agent_runtime/knowledge_engine/postgres_repository.py",
        "pg_advisory_xact_lock",
        "FOR UPDATE",
        "d.project_id=$2",
        "d.permission_scope='ORGANIZATION'",
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
        "parser_version",
        "chunker_version",
        "index_version",
        "embedding_space_id",
        "REVOKE DELETE",
    )
    if "raw_chat" in migration or "conversation_history" in migration:
        raise SystemExit("NODE-36 schema incorrectly stores conversation history")
    require(
        "apps/api/src/lumi_api/persistence/models/knowledge.py",
        '__tablename__ = "knowledge_documents"',
        '__tablename__ = "knowledge_chunks"',
        "permission_scope",
        "index_version",
        "embedding_space_id",
    )
    require(
        "apps/api/src/lumi_api/persistence/models/__init__.py",
        "KnowledgeChunkModel",
        "KnowledgeDocumentModel",
    )
    require(
        "scripts/integration_knowledge_engine.py",
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
