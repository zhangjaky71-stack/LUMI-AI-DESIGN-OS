from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "apps/api/alembic/versions"
AUTH_SRC = ROOT / "apps/api/src/lumi_api/auth"
POLICY_SRC = ROOT / "services/auth/src/lumi_auth"


def assert_contains(source: str, needle: str, label: str) -> None:
    if needle not in source:
        raise AssertionError(f"missing {label}: {needle}")


def validate_migrations() -> None:
    auth = (MIGRATIONS / "0004_auth_security.py").read_text(encoding="utf-8")
    roles = (MIGRATIONS / "0005_auth_role_hardening.py").read_text(encoding="utf-8")
    assert_contains(auth, 'down_revision = "0003_runtime_privilege_hardening"', "auth down revision")
    assert_contains(roles, 'down_revision = "0004_auth_security"', "role hardening down revision")
    for table in (
        "password_credentials",
        "email_verification_tokens",
        "password_reset_tokens",
        "organization_invites",
        "api_tokens",
    ):
        assert_contains(auth, f"CREATE TABLE {table}", f"auth table {table}")
    assert_contains(auth, "password_hash LIKE '$argon2id$%'", "Argon2id database check")
    assert_contains(auth, "csrf_token_hash", "session CSRF hash")
    assert_contains(auth, "revoked_at", "session revocation timestamp")
    assert_contains(auth, "secret_hash char(64)", "API token hash")
    assert_contains(roles, "SET role = upper(role)", "legacy role normalization")
    assert_contains(roles, "ck_organization_members_role", "organization role CHECK")
    for role in ("OWNER", "ADMIN", "EDITOR", "VIEWER", "BILLING"):
        assert_contains(roles, role, f"frozen role {role}")

    lowered = auth.lower()
    for forbidden in ("plaintext_password", "plaintext_token", "password varchar", "secret varchar"):
        if forbidden in lowered:
            raise AssertionError(f"plaintext credential field leaked into migration: {forbidden}")


def validate_password_adapter() -> None:
    source = (AUTH_SRC / "password.py").read_text(encoding="utf-8")
    assert_contains(source, "from argon2 import PasswordHasher", "mature Argon2 dependency")
    assert_contains(source, "type=Type.ID", "Argon2id selection")
    assert_contains(source, "check_needs_rehash", "password rehash policy")
    for forbidden in ("hashlib.pbkdf2", "bcrypt", "scrypt(", "sha256(password"):
        if forbidden in source:
            raise AssertionError(f"custom/incorrect password hashing detected: {forbidden}")


def validate_router_security() -> None:
    source = (AUTH_SRC / "router.py").read_text(encoding="utf-8")
    assert_contains(source, "httponly=True", "HttpOnly session cookie")
    assert_contains(source, "samesite=\"lax\"", "SameSite session cookie")
    assert_contains(source, "secure=secure_cookie", "Secure cookie configuration")
    assert_contains(source, "application/problem+json", "Problem Details errors")
    assert_contains(source, "status_code=202", "enumeration-safe accepted endpoints")
    assert_contains(source, "X-CSRF-Token", "CSRF header contract")
    if "email_verification_token" in source or "reset_plaintext" in source:
        raise AssertionError("HTTP router must not return verification/reset plaintext secret")


def validate_policy_dependency_boundary() -> None:
    forbidden = (
        "fastapi",
        "sqlalchemy",
        "alembic",
        "argon2",
        "langchain",
        "langgraph",
        "openai",
        "anthropic",
        "boto3",
        "httpx",
        "requests",
        "celery",
        "pika",
    )
    for path in sorted(POLICY_SRC.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
            for name in names:
                if name.startswith(forbidden):
                    raise AssertionError(f"policy layer leaked implementation dependency {name}")


def main() -> None:
    validate_migrations()
    validate_password_adapter()
    validate_router_security()
    validate_policy_dependency_boundary()
    print("Auth/Tenant security contract OK: migrations, Argon2id, cookie/CSRF and policy boundary validated")


if __name__ == "__main__":
    main()
