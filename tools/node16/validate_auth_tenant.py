from __future__ import annotations

import ast
import json
from pathlib import Path

from lumi_api.auth import OrganizationRole, Permission, role_permission_matrix

ROOT = Path(__file__).resolve().parents[2]
AUTH = ROOT / "apps" / "api" / "src" / "lumi_api" / "auth"
REPOSITORIES = ROOT / "apps" / "api" / "src" / "lumi_api" / "domain" / "repositories.py"
SESSION = ROOT / "apps" / "api" / "src" / "lumi_api" / "persistence" / "session.py"
RLS_SQL = ROOT / "apps" / "api" / "migrations" / "versions" / "20260816_0001_sql" / "up_07.sql"
MIGRATION = ROOT / "apps" / "api" / "migrations" / "versions" / "20260816_0002_auth_tenant.py"
UP_SQL = ROOT / "apps" / "api" / "migrations" / "versions" / "20260816_0002_sql" / "up_01.sql"
DOWN_SQL = ROOT / "apps" / "api" / "migrations" / "versions" / "20260816_0002_sql" / "down_01.sql"
GAPS = ROOT / "reports" / "nodes" / "NODE-16" / "gap-ledger.json"

EXPECTED_ROLES = {"OWNER", "ADMIN", "EDITOR", "VIEWER", "BILLING"}
EXPECTED_PERMISSIONS = {
    "project.read",
    "project.write",
    "asset.upload",
    "artifact.approve",
    "brand.manage",
    "member.invite",
    "member.manage",
    "billing.read",
    "billing.manage",
    "admin.audit.read",
    "api_token.manage",
}


def validate_role_matrix() -> None:
    if {role.value for role in OrganizationRole} != EXPECTED_ROLES:
        raise SystemExit("organization role registry changed without NODE-16 contract update")
    if {permission.value for permission in Permission} != EXPECTED_PERMISSIONS:
        raise SystemExit("permission registry changed without NODE-16 contract update")
    matrix = role_permission_matrix()
    if "project.write" in matrix["VIEWER"]:
        raise SystemExit("VIEWER must never have project.write")
    if "billing.manage" not in matrix["BILLING"]:
        raise SystemExit("BILLING must retain billing.manage")
    if "project.write" in matrix["BILLING"]:
        raise SystemExit("BILLING must not inherit project.write")


def validate_repository_tenant_scope() -> None:
    tree = ast.parse(REPOSITORIES.read_text(encoding="utf-8"), filename=str(REPOSITORIES))
    checked = 0
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in {"get", "save", "append"}:
            continue
        names = [argument.arg for argument in node.args.args]
        if names[:2] != ["self", "organization_id"]:
            raise SystemExit(
                f"tenant repository method {node.name} must begin self, organization_id: {names}"
            )
        checked += 1
    if checked < 12:
        raise SystemExit(f"expected >=12 tenant-scoped repository methods, got {checked}")


def validate_password_boundary() -> None:
    passwords = (AUTH / "passwords.py").read_text(encoding="utf-8")
    service = (AUTH / "service.py").read_text(encoding="utf-8")
    if 'import_module("argon2")' not in passwords:
        raise SystemExit("production password adapter must delegate to argon2-cffi")
    forbidden = ("hashlib.scrypt", "hashlib.pbkdf2", "bcrypt.hashpw")
    combined = passwords + service
    for marker in forbidden:
        if marker in combined:
            raise SystemExit(f"homegrown/alternate password implementation forbidden: {marker}")
    if "$argon2id$" not in passwords:
        raise SystemExit("Argon2id encoded hash contract missing")


def validate_migration_contract() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")
    if 'revision = "20260816_0002"' not in migration:
        raise SystemExit("NODE-16 migration revision is not frozen")
    if 'down_revision = "20260816_0001"' not in migration:
        raise SystemExit("NODE-16 migration must be forward-only from NODE-10 baseline")

    up = UP_SQL.read_text(encoding="utf-8")
    required_up = (
        "CREATE TABLE password_credentials",
        "CREATE TABLE auth_sessions",
        "CREATE TABLE auth_one_time_tokens",
        "CREATE TABLE api_tokens",
        "CREATE TABLE auth_security_events",
        "password_hash LIKE '$argon2id$%'",
        "role IN ('owner','admin','editor','viewer','billing')",
        "ALTER TABLE api_tokens ENABLE ROW LEVEL SECURITY",
        "tenant_isolation_api_tokens",
        "lumi_current_organization_id()",
    )
    for marker in required_up:
        if marker not in up:
            raise SystemExit(f"NODE-16 migration missing invariant: {marker}")

    down = DOWN_SQL.read_text(encoding="utf-8")
    required_down = (
        "DROP TABLE IF EXISTS auth_security_events",
        "DROP TABLE IF EXISTS api_tokens",
        "DROP TABLE IF EXISTS auth_one_time_tokens",
        "DROP TABLE IF EXISTS auth_sessions",
        "DROP TABLE IF EXISTS password_credentials",
        "role IN ('owner','admin','member','viewer')",
    )
    for marker in required_down:
        if marker not in down:
            raise SystemExit(f"NODE-16 rollback missing invariant: {marker}")


def validate_rls_bridge() -> None:
    session = SESSION.read_text(encoding="utf-8")
    if "app.current_organization_id" not in session or "set_config" not in session:
        raise SystemExit("tenant_session must set PostgreSQL tenant context")
    rls = RLS_SQL.read_text(encoding="utf-8")
    if "ENABLE ROW LEVEL SECURITY" not in rls:
        raise SystemExit("NODE-10 RLS baseline missing")
    if "lumi_current_organization_id()" not in rls:
        raise SystemExit("NODE-10 tenant RLS function boundary missing")


def validate_gap_ledger() -> None:
    ledger = json.loads(GAPS.read_text(encoding="utf-8"))
    gaps = ledger.get("gaps", [])
    if not gaps:
        raise SystemExit("NODE-16 gap ledger must remain explicit")
    ids = {gap["id"] for gap in gaps}
    if "AUTH-DEP-001" not in ids:
        raise SystemExit("argon2-cffi frozen-lock dependency gap must be tracked")
    if any(gap.get("status") == "IGNORED" for gap in gaps):
        raise SystemExit("security gaps may not be marked IGNORED")


def validate_no_plaintext_secret_fields() -> None:
    models = (AUTH / "models.py").read_text(encoding="utf-8")
    forbidden_fields = ("password: str", "token_secret: str", "session_secret: str")
    for marker in forbidden_fields:
        if marker in models:
            raise SystemExit(f"persistent auth model contains plaintext secret field: {marker}")


def main() -> None:
    validate_role_matrix()
    validate_repository_tenant_scope()
    validate_password_boundary()
    validate_migration_contract()
    validate_rls_bridge()
    validate_gap_ledger()
    validate_no_plaintext_secret_fields()
    print("NODE16_AUTH_TENANT_VALIDATION_PASS")
    print(f"roles={len(OrganizationRole)} permissions={len(Permission)}")
    print("tenant_repository_scope=PASS migration_0002=PASS rls_bridge=PASS")


if __name__ == "__main__":
    main()
