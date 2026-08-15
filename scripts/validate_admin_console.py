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
            raise AssertionError(f"missing contract marker: {needle}")


def main() -> None:
    domain = read("services/project-core/src/lumi_project_core/admin_console.py")
    api = read("apps/api/src/lumi_api/admin_router.py")
    page = read("apps/web/src/app/app/admin/page.tsx")
    component = read("apps/web/src/components/admin-console/admin-console.tsx")
    gateway = read("apps/web/src/lib/admin-console/admin-gateway.ts")
    shell_types = read("apps/web/src/lib/app-shell/types.ts")
    shell = read("apps/web/src/components/app-shell/app-shell-frame.tsx")
    spec = read("docs/nodes/NODE-64-ADMIN-CONSOLE.md")
    runtime = read("docs/runtime/ADMIN-CONSOLE-V1.md")
    acceptance = read("reports/nodes/NODE-64/acceptance.md")

    require(
        domain,
        "SUPPORT_READ",
        "BILLING_ADMIN",
        "SECURITY_AUDITOR",
        "PRIVACY_ADMIN",
        "admin.provider.manage",
        "admin.queue.requeue",
        "SensitiveActionConfirmation",
        'confirmation != "CONFIRM"',
        "timedelta(hours=24)",
        "expected_payload_sha256",
        "ADMIN_QUEUE_PAYLOAD_MUTATED",
        "ADMIN_PII_REVEALED",
        "ADMIN_VIEW_AS_MUST_BE_READONLY",
        "Node63CreditLedgerAdapter",
        'entry_type="ADJUSTMENT"',
        "require_non_negative=delta_credits < 0",
    )
    require(api, 'prefix="/admin"', "PlatformAdminActorResolver", "Idempotency-Key")
    require(page, "session.platform_admin", "platform-admin-required")
    require(shell_types, "PlatformAdminPrincipal", "platform_admin?:")
    require(shell, 'href: "/app/admin"', "Boolean(session.platform_admin)")
    require(component, "No arbitrary SQL", "Requeue original payload", "VIEW-AS · READ ONLY")
    require(spec, "IMPLEMENTED / VALIDATING / NOT COMPLETE", "NODE-65")
    require(runtime, "NODE-65", "immutable")
    require(acceptance, "STAGED", "NOT COMPLETE")

    frontend = component + gateway
    for forbidden in ("localStorage", "sessionStorage", "indexedDB", "card_number", "cvv", "cvc"):
        if forbidden in frontend:
            raise AssertionError(f"forbidden admin client persistence/payment marker: {forbidden}")
    for forbidden in ("execute_sql", "raw_sql", "kill_process", "update_payment_state"):
        if forbidden in domain + api:
            raise AssertionError(f"forbidden privileged escape hatch: {forbidden}")

    print("NODE-64 Admin Console contract: OK")


if __name__ == "__main__":
    main()
