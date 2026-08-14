from __future__ import annotations

import ast
from pathlib import Path

from lumi_agent_runtime.context_engine import ContextLayer, TrustLevel

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "apps/agent-runtime/src/lumi_agent_runtime/context_engine"
REQUIRED = {"__init__.py","budget.py","builder.py","cache.py","composite.py","compression.py","contracts.py","errors.py","invalidation.py","learning.py","postgres_source.py","profiles.py","render.py","retrieval.py","safety.py","source.py","static_source.py"}
FORBIDDEN_IMPORTS = {"asyncpg","sqlalchemy","psycopg","requests","subprocess","docker","openai","anthropic","google"}


def require(path: str, *markers: str) -> str:
    text=(ROOT/path).read_text(encoding="utf-8")
    for marker in markers:
        if marker not in text: raise SystemExit(f"{path}: missing NODE-34 marker: {marker}")
    return text


def main() -> int:
    missing=sorted(name for name in REQUIRED if not (PACKAGE/name).is_file())
    if missing: raise SystemExit(f"NODE-34 modules missing: {missing}")
    if [x.value for x in ContextLayer] != ["L0_SYSTEM","L1_PROJECT","L2_AGENT","L3_TASK","L4_RETRIEVED"]: raise SystemExit("NODE-34 layer contract drifted")
    if TrustLevel.TRUSTED_SYSTEM.value != "TRUSTED_SYSTEM": raise SystemExit("NODE-34 trust contract drifted")
    require("apps/agent-runtime/src/lumi_agent_runtime/context_engine/builder.py","request.context_budget_tokens","required_source_ids","CONTEXT_REQUIRED_LAYER_BUDGET_EXHAUSTED","CONTEXT_REQUIRED_SOURCE_NOT_INCLUDED","source_versions","cache_key")
    require("apps/agent-runtime/src/lumi_agent_runtime/context_engine/budget.py","render_context_item","conservative_token_estimate")
    safety=require("apps/agent-runtime/src/lumi_agent_runtime/context_engine/safety.py","UNTRUSTED_RETRIEVED_DATA","TRUSTED_PROJECT_DATA",'metadata["instruction_authority"] = "none"',"prompt_injection_suspected")
    if "project-data-only" in safety: raise SystemExit("NODE-34 project data authority marker drifted")
    require("apps/agent-runtime/src/lumi_agent_runtime/context_engine/retrieval.py","semantic_score","lexical_score","hybrid_score","candidate.organization_id == organization_id","candidate.project_id == project_id")
    postgres=require("apps/agent-runtime/src/lumi_agent_runtime/context_engine/postgres_source.py","FROM projects","brief_json","brief_version","brand_rules","FROM tasks","task_dependencies","FROM assets","asset_metadata","FROM artifacts","asset_embeddings","e.dimensions","query_embedding","UNTRUSTED_RETRIEVED")
    for forbidden in ("project_summaries","original_filename","e.dims","INSERT INTO","UPDATE ","DELETE FROM","chat_history","conversation_messages"):
        if forbidden in postgres: raise SystemExit(f"NODE-34 canonical/read-only source violation: {forbidden}")
    require("apps/agent-runtime/src/lumi_agent_runtime/context_engine/cache.py","source_versions","invalidate_project","invalidate_source_version","Process-local cache only")
    require("apps/agent-runtime/src/lumi_agent_runtime/context_engine/invalidation.py","project.summary.updated","artifact.version.created","task.succeeded")
    learning=require("apps/agent-runtime/src/lumi_agent_runtime/context_engine/learning.py","CorrectionSignal","LearningProposal","ProjectLearningPort","submit_correction","never stores raw chat history")
    for forbidden in ("raw_chat","chat_history","conversation_messages"):
        if forbidden in learning: raise SystemExit(f"NODE-34 learning stores forbidden history marker: {forbidden}")
    for path in PACKAGE.glob("*.py"):
        tree=ast.parse(path.read_text(encoding="utf-8"),filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                roots={alias.name.split(".",1)[0] for alias in node.names}
                if roots & FORBIDDEN_IMPORTS: raise SystemExit(f"Context Engine imports ambient authority: {path}")
            if isinstance(node,ast.ImportFrom) and node.module and node.module.split(".",1)[0] in FORBIDDEN_IMPORTS:
                raise SystemExit(f"Context Engine imports ambient authority: {path}")
    print("NODE-34 Context Engine static contract: PASS")
    return 0


if __name__ == "__main__": raise SystemExit(main())
