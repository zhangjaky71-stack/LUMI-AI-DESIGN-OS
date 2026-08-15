from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "services/project-core/src/lumi_project_core/approval.py",
    "services/project-core/tests/test_approval.py",
    "apps/agent-runtime/src/lumi_agent_runtime/recipe_engine/approval_bridge.py",
    "apps/agent-runtime/tests/test_approval_bridge.py",
    "apps/api/src/lumi_api/approval_router.py",
    "apps/api/tests/test_approval_router.py",
    "db/migrations/0012_approval_engine.sql",
    "apps/web/src/app/app/projects/[projectId]/approvals/page.tsx",
    "apps/web/src/components/approval-ui/approval-center.tsx",
    "apps/web/src/lib/approval-ui/types.ts",
    "apps/web/src/lib/approval-ui/contracts.ts",
    "apps/web/src/lib/approval-ui/approval-gateway.ts",
    "apps/web/src/lib/approval-ui/approval-server.ts",
    "apps/web/e2e/approval-ui.spec.ts",
    "docs/runtime/APPROVAL-ENGINE-V1.md",
    "reports/nodes/NODE-62/acceptance.md",
]
for relative in REQUIRED:
    if not (ROOT / relative).exists():
        raise SystemExit(f"NODE-62 missing required file: {relative}")

engine = (ROOT / "services/project-core/src/lumi_project_core/approval.py").read_text()
bridge = (ROOT / "apps/agent-runtime/src/lumi_agent_runtime/recipe_engine/approval_bridge.py").read_text()
migration = (ROOT / "db/migrations/0012_approval_engine.sql").read_text().lower()
frontend = "\n".join((ROOT / path).read_text() for path in [
    "apps/web/src/components/approval-ui/approval-center.tsx",
    "apps/web/src/lib/approval-ui/approval-gateway.ts",
    "apps/web/src/lib/approval-ui/approval-server.ts",
])

for token in [
    "CREATIVE_DIRECTION", "ARTIFACT_VERSION", "BUDGET_INCREASE", "EXTERNAL_PUBLISH",
    "CHANGES_REQUESTED", "SUPERSEDED", "APPROVAL_STALE", "idempotency_key",
    "ROLE_BASED_SEQUENCE", "ApprovalChangesPort", "ApprovalAuditEvent", "subject_version",
]:
    if token not in engine:
        raise SystemExit(f"NODE-62 domain contract missing {token}")
for token in ["interrupt", "Command", "approval_id", "subject_version"]:
    if token not in bridge:
        raise SystemExit(f"NODE-62 LangGraph bridge missing {token}")
for table in ["approvals", "approval_decisions", "approval_change_requests", "approval_audit_events"]:
    if f"create table if not exists {table}" not in migration:
        raise SystemExit(f"NODE-62 durable table missing: {table}")
for floating in ["'latest'", "'head'", "'current'"]:
    if floating not in migration:
        raise SystemExit("NODE-62 migration must fail closed on floating subject versions")
if "collaboration_notifications" not in (ROOT / "docs/runtime/APPROVAL-ENGINE-V1.md").read_text():
    raise SystemExit("NODE-62 must reuse NODE-61 notification truth")
for forbidden in ["localStorage", "sessionStorage", "indexedDB"]:
    if forbidden in frontend:
        raise SystemExit(f"NODE-62 browser canonical persistence forbidden: {forbidden}")
if 'process.env.NODE_ENV !== "production"' not in (ROOT / "apps/web/src/lib/approval-ui/approval-server.ts").read_text():
    raise SystemExit("NODE-62 deterministic fixture must be non-production gated")
project_page = (ROOT / "apps/web/src/app/app/projects/[projectId]/page.tsx").read_text()
if "/approvals" not in project_page:
    raise SystemExit("NODE-62 Project Approval entry missing")
print("NODE-62 Approval Engine architecture contract: OK")
