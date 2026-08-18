from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(haystack: str, needle: str, label: str) -> None:
    if needle not in haystack:
        raise SystemExit(f"NODE65_VALIDATION_FAILED:{label}:{needle}")


def forbid(haystack: str, needle: str, label: str) -> None:
    if needle in haystack:
        raise SystemExit(f"NODE65_VALIDATION_FAILED:{label}:{needle}")


def main() -> None:
    migration_py = read("apps/api/migrations/versions/20260818_0025_audit_governance.py")
    migration = read("apps/api/migrations/versions/20260818_0025_sql/up.sql")
    models = read("apps/api/src/lumi_api/persistence/models_platform.py")
    governance_models = read("apps/api/src/lumi_api/persistence/models_governance.py")
    contracts = read("apps/api/src/lumi_api/governance/contracts.py")
    redaction = read("apps/api/src/lumi_api/governance/redaction.py")
    repository = read("apps/api/src/lumi_api/governance/repository.py")
    service = read("apps/api/src/lumi_api/governance/service.py")
    factory = read("apps/api/src/lumi_api/governance/factory.py")
    dependencies = read("apps/api/src/lumi_api/api/v1/governance_dependencies.py")
    routes = read("apps/api/src/lumi_api/api/v1/governance_routes.py")
    app = read("apps/api/src/lumi_api/api/v1/app.py")
    policy = read("apps/api/src/lumi_api/auth/policy.py")
    admin_service = read("apps/api/src/lumi_api/admin/service.py")
    report = read("reports/nodes/NODE-65/implementation.md")
    ledger = json.loads(read("reports/nodes/NODE-65/gap-ledger.json"))

    require(migration_py, 'revision = "20260818_0025"', "migration revision")
    require(migration_py, 'down_revision = "20260818_0024"', "linear migration")

    require(migration, "node65_legacy_actor_type", "legacy actor preservation")
    require(migration, "node65_legacy_event_hash", "legacy hash preservation")
    require(migration, "ck_audit_events_actor_type", "actor constraint")
    require(migration, "ck_audit_events_event_hash", "hash constraint")
    require(migration, "trg_audit_events_immutable", "append-only trigger")
    require(migration, "BEFORE UPDATE OR DELETE ON audit_events", "append-only enforcement")
    for table in (
        "governance_retention_policies",
        "governance_legal_holds",
        "governance_deletion_requests",
        "governance_audit_exports",
    ):
        require(migration, f"CREATE TABLE {table}", f"table {table}")
    for retention_class in (
        "SECURITY_AUDIT",
        "BILLING",
        "CONTENT",
        "AGENT_TRACE",
        "TEMP_SANDBOX",
        "EXPORT",
        "ANALYTICS",
    ):
        require(migration, retention_class, f"retention {retention_class}")
    require(
        migration,
        "legal review required before jurisdictional launch",
        "legal non-claim",
    )

    require(models, "ck_audit_events_event_hash", "ORM hash constraint")
    require(models, "actor_id: Mapped[str]", "ORM non-null actor")
    require(governance_models, "GovernanceLegalHoldModel", "hold ORM")
    require(governance_models, "GovernanceDeletionRequestModel", "deletion ORM")
    require(governance_models, "GovernanceAuditExportModel", "export ORM")

    require(contracts, 'AGENT_AUDIT_REQUIRES_RUN', "agent run attribution")
    require(contracts, 'AGENT_AUDIT_REQUIRES_VERSION', "agent version attribution")
    require(contracts, 'AGENT_AUDIT_REQUIRES_HUMAN_INITIATOR', "human initiator")
    require(contracts, 'AGENT_AUDIT_SYSTEM_IDENTITY_FORBIDDEN', "system actor rejection")

    for secret_key in (
        "password",
        "authorization",
        "api_key",
        "access_token",
        "session_secret",
        "card_number",
        "private_key",
    ):
        require(redaction, secret_key, f"redaction key {secret_key}")
    require(redaction, "sha256_ref", "content hashing")
    require(redaction, "sanitize_url", "URL sanitization")
    require(redaction, "github_pat_", "secret-shaped free text")

    require(repository, "pg_advisory_xact_lock", "transaction lock")
    require(repository, "previous_hash", "audit chain")
    require(repository, "governance-hold:", "hold/erase serialization")
    require(repository, "NOT EXISTS", "live hold SQL fence")
    require(repository, "jsonb_array_length", "recorded hold fence")
    forbid(repository, ".commit()", "repository transaction ownership")
    forbid(repository, ".rollback()", "repository transaction ownership")

    require(service, "SubjectDeactivationPort", "deactivation port")
    require(service, "ObjectDeletionPort", "object deletion port")
    require(service, "SearchDeletionPort", "search deletion port")
    require(service, "GOVERNANCE_DELETION_PORTS_NOT_COMPOSED", "fail closed deletion")
    require(service, "GOVERNANCE_LEGAL_HOLD_BLOCKS_DELETION", "hold blocks deletion")
    require(service, "GOVERNANCE_AUDIT_EXPORT_PORT_NOT_COMPOSED", "fail closed export")
    require(service, "redact_audit_mapping(request.filters)", "export filter redaction")

    require(factory, "with session.begin()", "atomic request transaction")
    require(dependencies, "governance_service_not_composed", "fail closed composition")
    require(routes, 'APIRouter(prefix="/api/v1/governance"', "governance API prefix")
    require(app, "app.include_router(governance_router", "governance API registration")
    require(app, "dependencies=[Depends(enforce_api_auth)]", "authenticated route boundary")

    require(policy, 'AUDIT_EXPORT = "audit.export"', "audit export permission")
    require(policy, 'GOVERNANCE_MANAGE = "governance.manage"', "governance permission")
    require(admin_service, "redact_audit_text", "platform admin reason scrub")

    assert ledger["node"] == "NODE-65"
    assert ledger["status"] == "CORE_IMPLEMENTED_VALIDATING_NOT_COMPLETE"
    assert any(
        gap["severity"] == "P0" and gap["status"] == "open"
        for gap in ledger["gaps"]
    )
    assert any(
        gap["id"] == "NODE65-GAP-201" and gap["status"] == "closed"
        for gap in ledger["gaps"]
    )
    require(report, "does **not** currently claim", "explicit non-claims")

    print("NODE65_GOVERNANCE_STATIC_ACCEPTANCE_PASS")


if __name__ == "__main__":
    main()
