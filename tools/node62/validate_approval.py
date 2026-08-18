from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"NODE62_STATIC_ACCEPTANCE_FAIL: {message}")


def main() -> None:
    migration = read("apps/api/migrations/versions/20260818_0022_approval_engine.py")
    up_sql = read("apps/api/migrations/versions/20260818_0022_sql/up.sql")
    app = read("apps/api/src/lumi_api/api/v1/app.py")
    schemas = read("apps/api/src/lumi_api/api/v1/approval_schemas.py")
    routes = read("apps/api/src/lumi_api/api/v1/approval_routes.py")
    repository = read("apps/api/src/lumi_api/approvals/repository.py")
    effects = read("apps/api/src/lumi_api/approvals/effects.py")
    adapters = read("apps/api/src/lumi_api/approvals/adapters.py")
    legacy_schema = read("apps/api/src/lumi_api/api/v1/artifact_engine_schemas.py")
    workspace = read("apps/web/src/components/workspace/ai-workspace.tsx")
    timeline = read("apps/web/src/components/workspace/agent-timeline.tsx")
    panel = read("apps/web/src/components/approvals/approval-panel.tsx")
    web_types = read("apps/web/src/lib/approvals/types.ts")
    ledger = json.loads(read("reports/nodes/NODE-62/gap-ledger.json"))

    require('revision = "20260818_0022"' in migration, "approval migration revision mismatch")
    require('down_revision = "20260818_0021"' in migration, "approval migration must extend collaboration head")
    for table in ("approval_requests", "approval_decisions", "approval_audit_events", "approval_effects"):
        require(f"CREATE TABLE {table}" in up_sql, f"missing durable table {table}")

    require("request_operation_id UUID NOT NULL" in up_sql, "request operation idempotency missing")
    require("uq_approval_request_operation" in up_sql, "request idempotency uniqueness missing")
    require("uq_approval_decision_operation" in up_sql, "decision idempotency uniqueness missing")
    require("uq_approval_effect_operation" in up_sql, "effect idempotency uniqueness missing")
    require("subject_snapshot_hash" in up_sql, "exact subject snapshot missing")
    require("subject_id = artifact_version_id" in up_sql, "artifact exact subject constraint missing")

    require("from .approval_routes import router as approval_router" in app, "formal approval router import missing")
    require("app.include_router(approval_router" in app, "formal approval router is not mounted")
    require("Depends(enforce_api_auth)" in app.split("app.include_router(approval_router", 1)[1].split("\n", 1)[0], "approval router must be authenticated")

    create_schema = schemas.split("class CreateArtifactApprovalRequest", 1)[1].split("class ApprovalDecisionRequest", 1)[0]
    for forbidden in ("agent_run_id", "task_id", "interrupt_id", "resume_version"):
        require(forbidden not in create_schema, f"browser create schema must not accept {forbidden}")
    response_schema = schemas.split("class ApprovalResponse", 1)[1].split("class ApprovalEffectResponse", 1)[0]
    require("interrupt_id" not in response_schema and "resume_version" not in response_schema, "public Approval response leaks Graph controls")
    effect_schema = schemas.split("class ApprovalEffectResponse", 1)[1].split("class ApprovalDecisionResponse", 1)[0]
    require("payload" not in effect_schema and "last_error" not in effect_schema, "public effect response leaks internals")
    require("has_error" in effect_schema, "safe effect error projection missing")

    require("actor_id, permissions = _context(request)" in routes, "decision must derive authenticated actor and permissions")
    require("actor_permissions=permissions" in routes, "decision permissions are not forwarded to domain")
    require("required_permission not in command.actor_permissions" in repository, "domain permission fence missing")
    require("artifact.approve" in repository, "artifact approval permission missing")
    stale = repository.split("def _artifact_stale_code", 1)[1].split("def _validate_runtime_links", 1)[0]
    require("subject_snapshot_hash" in stale and "READY" in stale, "exact version stale check incomplete")
    for forbidden in ("head_version_id", "artifact_branches", "latest_version"):
        require(forbidden not in stale, f"approval must not drift to branch head: {forbidden}")

    require("APPROVAL_EFFECT_ALREADY_RUNNING" in effects, "effect claim concurrency fence missing")
    require("attempt_count=attempt_count+1" in effects, "effect retry accounting missing")
    require('kind="approval"' in adapters, "Agent resume must use formal approval kind")
    require('"approval_id"' in adapters and '"decision"' in adapters, "Agent resume payload must include approval id and decision")

    legacy = legacy_schema.split("class ApproveVersionRequest", 1)[1].split("class MarkReadyRequest", 1)[0]
    require("approved_by_id:" not in legacy, "legacy direct approval still accepts approver identity")
    require("DIRECT_ARTIFACT_APPROVAL_DISABLED_USE_FORMAL_APPROVAL_ENGINE" in legacy, "legacy direct approval must fail closed")

    require("resumeAgentRun" not in workspace, "Workspace must not directly resume Graph for business approval")
    require("ApprovalPanel" in workspace, "Formal ApprovalPanel not mounted")
    require("permissions={permissions}" in workspace, "ApprovalPanel permission projection missing")
    require("currentArtifact={selectedArtifact}" in workspace, "ApprovalPanel must bind selected exact artifact")
    require("formal Approval decision" in timeline, "technical interrupt governance note missing")
    require('permissions.includes(active.requiredPermission)' in panel, "approval decision control permission projection missing")
    require("artifactVersionId === currentArtifact.artifactVersionId" in panel, "approval panel exact-version filter missing")
    for forbidden in ("interrupt_id", "resume_version", "payload_json", "last_error"):
        require(f'"{forbidden}"' in web_types, f"web parser must fail closed on {forbidden}")

    require(ledger["node"] == "NODE-62", "gap ledger node mismatch")
    require(ledger["status"] == "CORE_IMPLEMENTED_VALIDATING_NOT_COMPLETE", "gap ledger status mismatch")
    require(any(gap["severity"] == "P0" and gap["status"] == "open" for gap in ledger["gaps"]), "open P0 gaps must remain explicit")
    require(any(gap["id"] == "NODE62-GAP-013" and gap["status"] == "closed" for gap in ledger["gaps"]), "legacy UI direct Graph bypass gap should be closed")
    require(any(gap["id"] == "NODE62-GAP-014" and gap["status"] == "closed" for gap in ledger["gaps"]), "client approver identity gap should be closed")

    print("NODE62_STATIC_ACCEPTANCE_PASS")


if __name__ == "__main__":
    main()
