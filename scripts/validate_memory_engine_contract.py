from __future__ import annotations

import ast
from pathlib import Path

from lumi_agent_runtime.memory_engine import MemoryKind, MemoryScope

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "apps/agent-runtime/src/lumi_agent_runtime/memory_engine"
REQUIRED = {
    "__init__.py",
    "context_source.py",
    "contracts.py",
    "deep_adapter.py",
    "deep_provider.py",
    "errors.py",
    "governance.py",
    "pipeline.py",
    "policy.py",
    "postgres_repository.py",
    "repository.py",
    "retrieval.py",
    "sensitivity.py",
    "service.py",
}
FORBIDDEN_RUNTIME_IMPORTS = {
    "asyncpg",
    "sqlalchemy",
    "psycopg",
    "requests",
    "docker",
    "openai",
    "anthropic",
    "google",
}


def require(path: str, *markers: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    for marker in markers:
        if marker not in text:
            raise SystemExit(f"{path}: missing NODE-35 marker: {marker}")
    return text


def main() -> int:
    missing = sorted(name for name in REQUIRED if not (PACKAGE / name).is_file())
    if missing:
        raise SystemExit(f"NODE-35 Memory modules missing: {missing}")
    if {item.value for item in MemoryScope} != {
        "SESSION",
        "USER",
        "PROJECT",
        "BRAND",
        "AGENT",
        "ORGANIZATION",
    }:
        raise SystemExit("NODE-35 memory scope vocabulary drifted")
    if {item.value for item in MemoryKind} != {
        "PREFERENCE",
        "FACT",
        "DECISION",
        "CONSTRAINT_PREFERENCE",
        "WORKFLOW_LEARNING",
        "EPISODIC_SUMMARY",
    }:
        raise SystemExit("NODE-35 memory kind vocabulary drifted")

    contracts = require(
        "apps/agent-runtime/src/lumi_agent_runtime/memory_engine/contracts.py",
        "MemorySourceRef",
        "explicit_remember",
        "temporal_coexistence",
        "supersedes_id",
        "retention_hold",
        "embedding_model",
        "embedding_version",
    )
    if "raw_chat" in contracts or "conversation_history" in contracts:
        raise SystemExit("NODE-35 Memory contract contains raw-chat storage")

    pipeline = require(
        "apps/agent-runtime/src/lumi_agent_runtime/memory_engine/pipeline.py",
        "REJECT_SENSITIVE",
        "REJECT_SCOPE",
        "BRAND_RULE_PROPOSAL",
        "REQUIRE_CONFIRMATION",
        "DEDUPLICATE_CONFIRM",
        "MEMORY_EXACT_DUPLICATE_CONFIRMED",
        "supersedes_id",
    )
    sensitive_block = pipeline.split(
        'if sensitivity.classification.value != "NONE":', 1
    )[1].split("policy =", 1)[0]
    if "insert_candidate" in sensitive_block:
        raise SystemExit("NODE-35 persists rejected sensitive candidate content")
    rejected_scope = pipeline.split("if not policy.allowed:", 1)[1].split(
        "if policy.outcome", 1
    )[0]
    if "insert_candidate" in rejected_scope:
        raise SystemExit("NODE-35 persists rejected scope-spoofed candidate content")

    require(
        "apps/agent-runtime/src/lumi_agent_runtime/memory_engine/policy.py",
        "MEMORY_AGENT_SCOPE_DENIED",
        "MEMORY_AGENT_BRAND_WRITE_DENIED",
        "MEMORY_USER_SCOPE_DENIED",
        "memory.organization.read",
        "scope_matches_access",
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/memory_engine/sensitivity.py",
        "CREDENTIAL",
        "PAYMENT",
        "HEALTH",
        "PRIVATE KEY",
        "api[_ -]?key",
    )
    retrieval = require(
        "apps/agent-runtime/src/lumi_agent_runtime/memory_engine/retrieval.py",
        "can_read_scope",
        "scope_score",
        "lexical_score",
        "semantic_score",
        "confidence_score",
        "freshness_score",
    )
    if retrieval.index("can_read_scope") > retrieval.index("score = min"):
        raise SystemExit("NODE-35 retrieval scores before permission/scope filtering")

    require(
        "apps/agent-runtime/src/lumi_agent_runtime/memory_engine/governance.py",
        "retention_hold",
        "MemoryStatus.EXPIRED",
        "MemoryStatus.SUPERSEDED",
        "consolidated_into",
        "source_refs",
    )
    postgres = require(
        "apps/agent-runtime/src/lumi_agent_runtime/memory_engine/postgres_repository.py",
        "pg_advisory_xact_lock",
        "FOR UPDATE",
        "version=version+1",
        "MEMORY_REJECTED_CONTENT_MUST_NOT_PERSIST",
        "json.dumps",
        "_decode_vector",
    )
    for forbidden in FORBIDDEN_RUNTIME_IMPORTS:
        if f"import {forbidden}" in postgres or f"from {forbidden}" in postgres:
            raise SystemExit(f"NODE-35 Postgres repository imports concrete SDK: {forbidden}")

    require(
        "apps/agent-runtime/src/lumi_agent_runtime/memory_engine/context_source.py",
        "ContextKind.MEMORY",
        '"instruction_authority": "none"',
        "MemorySearchQuery",
        "query_embedding",
    )
    deep = require(
        "apps/agent-runtime/src/lumi_agent_runtime/memory_engine/deep_adapter.py",
        "class DeepAgentMemoryStore(BaseStore)",
        '_VIRTUAL_NAMESPACE = ("memory",)',
        "MEMORY_STORE_NAMESPACE_DENIED",
        "MemoryCandidate",
        "MemorySearchQuery",
    )
    if "organization_id = value" in deep or "scope_id = value" in deep:
        raise SystemExit("NODE-35 Deep Agent store accepts model-controlled tenant scope")
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/memory_engine/deep_provider.py",
        "DeepAgentMemoryStoreProvider",
        "store_for_run",
        "deep_agent_project_memory_store",
    )

    migration = require(
        "apps/api/alembic/versions/0016_memory_engine.py",
        'down_revision = "0015_task_graph_runtime"',
        "CREATE TABLE memory_records",
        "CREATE TABLE memory_candidates",
        "embedding vector",
        "REVOKE DELETE ON memory_records, memory_candidates FROM lumi_app",
    )
    if "raw_chat" in migration or "conversation_history" in migration:
        raise SystemExit("NODE-35 schema contains raw-chat memory storage")
    require(
        "apps/api/src/lumi_api/persistence/models/memory.py",
        '__tablename__ = "memory_records"',
        '__tablename__ = "memory_candidates"',
        "Vector()",
        "retention_hold",
        "supersedes_id",
    )
    require(
        "scripts/integration_memory_engine.py",
        "asyncio.gather",
        "DEDUPLICATE_CONFIRM",
        "REQUIRE_CONFIRMATION",
        "SUPERSEDED",
        "InsufficientPrivilegeError",
        "embedding::text",
    )
    require(
        "scripts/validate_context_eval_contract.py",
        "memory-retrieval-v1",
        "all eight categories",
    )
    require(
        "scripts/run_context_eval_report.py",
        "write_report",
        "compare_to_baseline",
    )

    for path in PACKAGE.glob("*.py"):
        if path.name == "postgres_repository.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".", 1)[0] for alias in node.names}
                if roots & FORBIDDEN_RUNTIME_IMPORTS:
                    raise SystemExit(f"Memory Engine imports ambient authority: {path}")
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".", 1)[0] in FORBIDDEN_RUNTIME_IMPORTS:
                    raise SystemExit(f"Memory Engine imports ambient authority: {path}")

    print("NODE-35 Memory Engine static contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
