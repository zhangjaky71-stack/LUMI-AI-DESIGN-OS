from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(haystack: str, needle: str, label: str) -> None:
    if needle not in haystack:
        raise SystemExit(f"NODE64_VALIDATION_FAILED:{label}:{needle}")


def forbid(haystack: str, needle: str, label: str) -> None:
    if needle in haystack:
        raise SystemExit(f"NODE64_VALIDATION_FAILED:{label}:{needle}")


def main() -> None:
    migration_py = read("apps/api/migrations/versions/20260818_0024_admin_console.py")
    migration = read("apps/api/migrations/versions/20260818_0024_sql/up.sql")
    contracts = read("apps/api/src/lumi_api/admin/contracts.py")
    service = read("apps/api/src/lumi_api/admin/service.py")
    repo = read("apps/api/src/lumi_api/admin/repository.py")
    safe_repo = read("apps/api/src/lumi_api/admin/repository_safe.py")
    factory = read("apps/api/src/lumi_api/admin/factory.py")
    auth_guard = read("apps/api/src/lumi_api/api/v1/admin_auth_guard.py")
    routes = read("apps/api/src/lumi_api/api/v1/admin_routes.py")
    app = read("apps/api/src/lumi_api/api/v1/app.py")
    web = read("apps/admin/src/components/admin-console.tsx")
    web_api = read("apps/admin/src/lib/admin/api.ts")
    web_types = read("apps/admin/src/lib/admin/types.ts")

    require(migration_py, 'down_revision = "20260818_0023"', "linear migration")
    for table in (
        "platform_admin_principals",
        "platform_admin_audit_events",
        "platform_feature_flags",
        "platform_break_glass_grants",
    ):
        require(migration, f"CREATE TABLE {table}", f"table {table}")

    require(migration, "trg_platform_admin_audit_immutable", "append-only admin audit")
    require(migration, "trg_platform_break_glass_immutable", "append-only break glass")
    require(migration, "uq_platform_feature_flag_scope", "feature flag scope uniqueness")
    require(contracts, 'SUPPORT_READ = "SUPPORT_READ"', "platform support role")
    require(contracts, 'SUPER_ADMIN = "SUPER_ADMIN"', "platform super admin role")
    forbid(contracts, 'OWNER = "OWNER"', "organization role leakage")
    require(factory, "principal_for_user", "dedicated platform principal lookup")
    require(factory, "PLATFORM_ADMIN_PRINCIPAL_REQUIRED", "org owner not implicit admin")
    require(auth_guard, "platform_admin_user_id", "admin identity boundary")
    require(app, "app.include_router(admin_router", "admin router installation")
    require(service, 'self.require("queue.manage")', "DLQ mutation permission")
    require(service, 'self.require("provider.manage"', "high-risk provider permission")
    require(service, 'self.require("security.breakglass")', "break-glass permission")
    require(service, "ADMIN_RELEASE_GATE_EVIDENCE_NOT_COMPOSED", "registry fail closed")
    require(repo, "admin-dlq-replay:", "stable replay idempotency key")
    require(repo, "FROM cost_ledger", "provider cost observability")
    forbid(repo, "UPDATE cost_ledger", "cost ledger mutation")
    forbid(repo, "INSERT INTO cost_ledger", "cost ledger mutation")
    require(safe_repo, "security_locked", "security flag mutation fence")
    require(routes, '@router.post("/break-glass"', "break-glass API")
    require(web, "Organization OWNER is not Platform Admin", "admin boundary UX")
    require(web, "Payload hidden by contract", "private DLQ payload UX")
    require(web, "ADMIN_RELEASE_GATE_EVIDENCE_NOT_COMPOSED", "registry fail-closed UX")
    require(web_api, 'headers.set("X-CSRF-Token", csrf)', "unsafe request CSRF")
    require(web_types, '"SUPER_ADMIN"', "frontend role parser")
    forbid(web, "private_prompt", "private prompt rendering")
    print("NODE64_ADMIN_STATIC_ACCEPTANCE_PASS")


if __name__ == "__main__":
    main()
