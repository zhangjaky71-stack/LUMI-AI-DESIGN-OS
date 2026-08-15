from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    value = (ROOT / path).read_text(encoding="utf-8")
    if not value.strip():
        raise AssertionError(f"empty required file: {path}")
    return value


def require(text: str, *needles: str) -> None:
    for needle in needles:
        if needle not in text:
            raise AssertionError(f"missing governance contract marker: {needle}")


def main() -> None:
    domain = read("services/project-core/src/lumi_project_core/governance.py")
    tests = read("services/project-core/tests/test_governance.py")
    api = read("apps/api/src/lumi_api/governance_router.py")
    migration = read("db/migrations/0014_audit_governance.sql")
    component = read("apps/web/src/components/governance/governance-center.tsx")
    gateway = read("apps/web/src/lib/governance/governance-gateway.ts")
    server = read("apps/web/src/lib/governance/governance-server.ts")
    spec = read("docs/nodes/NODE-65-AUDIT-GOVERNANCE.md")
    runtime = read("docs/runtime/AUDIT-GOVERNANCE-V1.md")
    acceptance = read("reports/nodes/NODE-65/acceptance.md")

    require(
        domain,
        "AuditEvent",
        "correction_of_event_id",
        "event_hash",
        "prev_hash",
        "sanitize_metadata",
        "GOVERNANCE_AGENT_IDENTITY_INCOMPLETE",
        "RetentionPolicy",
        "LegalHoldEvent",
        "DeletionEvent",
        "AUDIT_EXPORT_TOO_LARGE",
        "Node64AdminAuditSink",
        "gc_object",
        "remove_search_ref",
    )
    for retention_class in (
        "SECURITY_AUDIT",
        "BILLING",
        "CONTENT",
        "AGENT_TRACE",
        "TEMP_SANDBOX",
        "EXPORT",
        "ANALYTICS",
    ):
        require(domain, retention_class)
    require(
        migration,
        "governance_reject_mutation",
        "audit_events_append_only",
        "BEFORE UPDATE OR DELETE ON audit_events",
        "REVOKE UPDATE, DELETE ON audit_events FROM PUBLIC",
        "governance_retention_policies",
        "governance_legal_hold_events",
        "governance_deletion_events",
        "governance_audit_export_jobs",
        "status IN ('READY','EXPIRED')",
    )
    require(
        api,
        'prefix="/governance"',
        '"/capabilities"',
        '"can_export_audit": "audit.export" in actor.permissions',
        '_require_permission(actor, "audit.export")',
        "/audit/exports",
        "/legal-holds",
        "/deletions",
    )
    require(component, "Audit, Retention & Data Governance", "BLOCKED_HOLD", "Get fresh download")
    require(
        gateway,
        "DeterministicGovernanceGateway",
        "HttpGovernanceGateway",
        'get<GovernanceCapabilities>("/governance/capabilities"',
    )
    require(server, "LUMI_GOVERNANCE_E2E", "node65_governance_fixture_v1")
    require(tests, "verify_hash_chains", "Node64AdminAuditSink", "BLOCKED_HOLD")
    require(spec, "IMPLEMENTED / VALIDATING / NOT COMPLETE", "NODE-66")
    require(runtime, "append-only", "Legal Hold", "signed URL")
    require(acceptance, "STAGED", "NOT COMPLETE")

    if "signed_url" in migration.lower():
        raise AssertionError("signed URL must not be persisted in governance schema")
    for forbidden_column in (
        "password text",
        "api_key text",
        "session_secret text",
        "authorization text",
        "card_number",
        " cvc ",
        " cvv ",
    ):
        if forbidden_column in migration.lower():
            raise AssertionError(f"forbidden secret-bearing schema marker: {forbidden_column}")
    for forbidden in ("@router.put(\"/audit", "@router.delete(\"/audit"):
        if forbidden in api:
            raise AssertionError(f"ordinary audit mutation route is forbidden: {forbidden}")
    frontend = component + gateway
    for forbidden in ("localStorage", "sessionStorage", "indexedDB"):
        if forbidden in frontend:
            raise AssertionError(f"governance canonical client persistence is forbidden: {forbidden}")

    print("NODE-65 Audit Governance contract: OK")


if __name__ == "__main__":
    main()
