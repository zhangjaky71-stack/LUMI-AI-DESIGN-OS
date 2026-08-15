from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = [
    "services/project-core/src/lumi_project_core/collaboration.py",
    "services/project-core/tests/test_collaboration.py",
    "apps/api/src/lumi_api/collaboration_router.py",
    "apps/api/tests/test_collaboration_router.py",
    "db/migrations/0011_collaboration.sql",
    "apps/web/src/app/app/projects/[projectId]/collaboration/page.tsx",
    "apps/web/src/components/collaboration/collaboration.tsx",
    "apps/web/src/lib/collaboration/types.ts",
    "apps/web/src/lib/collaboration/contracts.ts",
    "apps/web/src/lib/collaboration/collaboration-gateway.ts",
    "apps/web/src/lib/collaboration/collaboration-server.ts",
    "apps/web/e2e/collaboration.spec.ts",
    "docs/runtime/COLLABORATION-V1.md",
    "reports/nodes/NODE-61/acceptance.md",
]

for relative in REQUIRED:
    if not (ROOT / relative).exists():
        raise SystemExit(f"NODE-61 missing required file: {relative}")

engine = (ROOT / "services/project-core/src/lumi_project_core/collaboration.py").read_text()
router = (ROOT / "apps/api/src/lumi_api/collaboration_router.py").read_text()
migration = (ROOT / "db/migrations/0011_collaboration.sql").read_text().lower()
frontend = "\n".join(
    path.read_text()
    for path in [
        ROOT / "apps/web/src/components/collaboration/collaboration.tsx",
        ROOT / "apps/web/src/lib/collaboration/contracts.ts",
        ROOT / "apps/web/src/lib/collaboration/collaboration-gateway.ts",
        ROOT / "apps/web/src/lib/collaboration/collaboration-server.ts",
    ]
)

for token in [
    "CommentAnchor",
    "PresenceState",
    "OperationConflict",
    "submit_operations",
    "reconnect",
    "COLLABORATION_HARD_CONSTRAINT_FAILED",
    "local_edit_preserved",
    "agent_run_id",
]:
    if token not in engine:
        raise SystemExit(f"NODE-61 engine contract missing {token}")

for token in [
    "resolve_http_context",
    "resolve_ws_context",
    "resolve_workspace_metadata",
    "AWARENESS_UPDATE",
    "COLLABORATION_CANONICAL_WRITE_REQUIRES_HTTP_OPERATION_API",
]:
    if token not in router:
        raise SystemExit(f"NODE-61 router contract missing {token}")

if "create table" in migration and "collaboration_presence" in migration:
    raise SystemExit("NODE-61 presence must not be a durable SQL table")
for table in [
    "collaboration_threads",
    "collaboration_comments",
    "collaboration_operation_commits",
    "collaboration_audit_events",
    "collaboration_notifications",
]:
    if f"create table if not exists {table}" not in migration:
        raise SystemExit(f"NODE-61 durable table missing: {table}")

for forbidden in ["localStorage", "sessionStorage", "indexedDB"]:
    if forbidden in frontend:
        raise SystemExit(f"NODE-61 browser canonical persistence forbidden: {forbidden}")

for required in [
    "HTTP Design Operation API",
    "CRDT/realtime state is never the sole design history",
    "Hard Constraints execute server-side",
    "LUMI_COLLABORATION_E2E",
]:
    if required not in frontend:
        raise SystemExit(f"NODE-61 frontend truth boundary missing: {required}")

server = (ROOT / "apps/web/src/lib/collaboration/collaboration-server.ts").read_text()
if 'process.env.NODE_ENV !== "production"' not in server:
    raise SystemExit("NODE-61 deterministic fixture must be non-production gated")

project_page = (ROOT / "apps/web/src/app/app/projects/[projectId]/page.tsx").read_text()
if "/collaboration" not in project_page:
    raise SystemExit("NODE-61 Project entry link missing")

print("NODE-61 collaboration architecture contract: OK")
