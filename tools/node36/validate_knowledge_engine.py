from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "apps/agent-runtime/src/lumi_agent_runtime/knowledge_engine"
TEST = ROOT / "apps/agent-runtime/tests/test_knowledge_engine_node36.py"
DURABLE_TEST = ROOT / "apps/agent-runtime/tests/test_knowledge_durable_node36.py"
FIXTURE = ROOT / "benchmarks/knowledge/hybrid-retrieval-v1.jsonl"
GAP_LEDGER = ROOT / "reports/nodes/NODE-36/gap-ledger.json"

FORBIDDEN_IMPORTS = {
    "openai",
    "anthropic",
    "langchain",
    "langgraph",
    "sqlalchemy",
    "psycopg",
    "pgvector",
    "chromadb",
    "pinecone",
    "weaviate",
    "qdrant_client",
    "requests",
    "subprocess",
}


def imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    output: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            output.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            output.add(node.module.split(".", 1)[0])
    return output


def main() -> None:
    required = {
        "__init__.py",
        "contracts.py",
        "engine.py",
        "store.py",
        "context_source.py",
        "embedding_port.py",
        "extraction.py",
        "ingestion.py",
    }
    actual = {path.name for path in PACKAGE.glob("*.py")}
    missing = sorted(required - actual)
    if missing:
        raise SystemExit(f"NODE36_MISSING_FILES:{','.join(missing)}")

    forbidden: dict[str, list[str]] = {}
    for path in PACKAGE.glob("*.py"):
        found = sorted(imports(path) & FORBIDDEN_IMPORTS)
        if found:
            forbidden[path.name] = found
    if forbidden:
        raise SystemExit(f"NODE36_FORBIDDEN_IMPORTS:{forbidden}")

    source = "\n".join(path.read_text(encoding="utf-8") for path in PACKAGE.glob("*.py"))
    assertions = {
        "untrusted_context": "TrustLevel.UNTRUSTED_RETRIEVED" in source,
        "zero_authority": "InstructionAuthority.NONE" in source,
        "permission_prefilter": "visible_candidates" in source,
        "citations": "KnowledgeCitation" in source,
        "stale": "KNOWLEDGE_STALE_SOURCE_PRESENT" in source,
        "hybrid": "lexical_score" in source and "vector_score" in source,
        "durable_store": "GitWorkspaceKnowledgeStore" in source,
        "atomic_head": "os.replace" in source and "head.json" in source,
        "rollback": "rollback_index" in source and "activate_document" in source,
        "version_identity": "index_version" in source and "content_hash" in source,
        "native_first": "extract_native_then_ocr" in source,
        "ocr_fallback": "extract_ocr" in source,
        "embedding_port": "class KnowledgeEmbeddingPort" in source,
        "no_old_version_resurrection": "_source_heads" in source,
    }
    failed = sorted(key for key, value in assertions.items() if not value)
    if failed:
        raise SystemExit(f"NODE36_CONTRACT_ASSERTION_FAILED:{','.join(failed)}")

    rows = [
        json.loads(line)
        for line in FIXTURE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(rows) < 12:
        raise SystemExit("NODE36_FIXTURE_COUNT_TOO_SMALL")
    ids = [row["id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise SystemExit("NODE36_FIXTURE_ID_DUPLICATE")

    ledger = json.loads(GAP_LEDGER.read_text(encoding="utf-8"))
    if ledger.get("node") != "NODE-36":
        raise SystemExit("NODE36_GAP_LEDGER_INVALID")
    if not isinstance(ledger.get("gaps"), list):
        raise SystemExit("NODE36_GAP_LEDGER_GAPS_INVALID")

    if not TEST.is_file() or not DURABLE_TEST.is_file():
        raise SystemExit("NODE36_TEST_MISSING")

    print("NODE36_KNOWLEDGE_ENGINE_VALIDATION_PASS")
    print(f"fixtures={len(rows)}")
    print(f"gaps={len(ledger['gaps'])}")


if __name__ == "__main__":
    main()
