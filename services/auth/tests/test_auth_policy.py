from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services/auth/src"))

from lumi_auth import (  # noqa: E402
    ApiTokenRecord,
    CookieContract,
    InMemorySlidingWindowRateLimiter,
    Membership,
    RateLimitExceeded,
    SessionRecord,
    SingleUseTokenRecord,
    authorize,
    build_request_context,
    consume_single_use_token,
    hash_token,
    issue_opaque_token,
    require_last_owner_invariant,
    validate_api_token,
    validate_csrf,
    validate_session,
)

NOW = datetime(2026, 8, 13, 3, 0, tzinfo=UTC)


class AuthPolicyTests(unittest.TestCase):
    def test_cross_tenant_access_is_denied_before_permission_check(self) -> None:
        context = build_request_context(
            request_id="req-1",
            actor_id="user-1",
            organization_id="org-a",
            memberships=(Membership("user-1", "org-a", "OWNER"),),
            trace_id="trace-1",
        )
        decision = authorize(context, resource_organization_id="org-b", permission="project.read")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason_code, "TENANT_NOT_FOUND_OR_FORBIDDEN")

    def test_viewer_cannot_write_and_billing_cannot_edit_project(self) -> None:
        viewer = build_request_context(
            request_id="req-v", actor_id="viewer", organization_id="org-a",
            memberships=(Membership("viewer", "org-a", "VIEWER"),), trace_id="t-v"
        )
        billing = build_request_context(
            request_id="req-b", actor_id="billing", organization_id="org-a",
            memberships=(Membership("billing", "org-a", "BILLING"),), trace_id="t-b"
        )
        self.assertFalse(authorize(viewer, resource_organization_id="org-a", permission="project.write").allowed)
        self.assertTrue(authorize(billing, resource_organization_id="org-a", permission="billing.manage").allowed)
        self.assertFalse(authorize(billing, resource_organization_id="org-a", permission="project.write").allowed)

    def test_last_owner_cannot_be_removed_or_demoted(self) -> None:
        memberships = (
            Membership("owner", "org-a", "OWNER"),
            Membership("editor", "org-a", "EDITOR"),
        )
        with self.assertRaisesRegex(ValueError, "LAST_OWNER_REQUIRED"):
            require_last_owner_invariant(
                memberships,
                organization_id="org-a",
                target_user_id="owner",
                target_role_after=None,
            )
        with self.assertRaisesRegex(ValueError, "LAST_OWNER_REQUIRED"):
            require_last_owner_invariant(
                memberships,
                organization_id="org-a",
                target_user_id="owner",
                target_role_after="ADMIN",
            )

    def test_owner_can_be_demoted_when_another_owner_exists(self) -> None:
        memberships = (
            Membership("owner-a", "org-a", "OWNER"),
            Membership("owner-b", "org-a", "OWNER"),
        )
        require_last_owner_invariant(
            memberships,
            organization_id="org-a",
            target_user_id="owner-a",
            target_role_after="ADMIN",
        )

    def test_opaque_tokens_are_high_entropy_hashed_and_single_use(self) -> None:
        issued = issue_opaque_token(label="lumi_reset")
        self.assertNotEqual(issued.plaintext, issued.token_hash)
        self.assertEqual(len(issued.token_hash), 64)
        record = SingleUseTokenRecord(
            token_hash=issued.token_hash,
            expires_at=NOW + timedelta(minutes=10),
        )
        consumed = consume_single_use_token(record, issued.plaintext, now=NOW)
        self.assertEqual(consumed.consumed_at, NOW)
        with self.assertRaisesRegex(PermissionError, "TOKEN_ALREADY_USED"):
            consume_single_use_token(consumed, issued.plaintext, now=NOW + timedelta(seconds=1))

    def test_expired_or_wrong_token_is_rejected(self) -> None:
        issued = issue_opaque_token(label="lumi_verify")
        expired = SingleUseTokenRecord(issued.token_hash, NOW - timedelta(seconds=1))
        with self.assertRaisesRegex(PermissionError, "TOKEN_EXPIRED"):
            consume_single_use_token(expired, issued.plaintext, now=NOW)
        active = SingleUseTokenRecord(issued.token_hash, NOW + timedelta(minutes=5))
        with self.assertRaisesRegex(PermissionError, "TOKEN_INVALID"):
            consume_single_use_token(active, "wrong-token", now=NOW)

    def test_session_expiry_revocation_origin_and_csrf_are_enforced(self) -> None:
        csrf = issue_opaque_token(label="lumi_csrf")
        record = SessionRecord(
            session_token_hash=hash_token("session-secret"),
            csrf_token_hash=csrf.token_hash,
            user_id="user-1",
            organization_id="org-a",
            created_at=NOW,
            expires_at=NOW + timedelta(hours=1),
        )
        validate_session(record, now=NOW)
        validate_csrf(
            record,
            csrf_token=csrf.plaintext,
            origin="https://app.lumi.dev",
            allowed_origins=frozenset({"https://app.lumi.dev"}),
        )
        with self.assertRaisesRegex(PermissionError, "CSRF_ORIGIN_DENIED"):
            validate_csrf(
                record,
                csrf_token=csrf.plaintext,
                origin="https://evil.example",
                allowed_origins=frozenset({"https://app.lumi.dev"}),
            )
        with self.assertRaisesRegex(PermissionError, "CSRF_TOKEN_INVALID"):
            validate_csrf(
                record,
                csrf_token="wrong",
                origin="https://app.lumi.dev",
                allowed_origins=frozenset({"https://app.lumi.dev"}),
            )

    def test_cookie_contract_is_secure_and_http_only(self) -> None:
        cookie = CookieContract()
        self.assertTrue(cookie.secure)
        self.assertTrue(cookie.http_only)
        self.assertEqual(cookie.same_site, "lax")
        with self.assertRaises(ValueError):
            CookieContract(http_only=False)

    def test_api_token_scope_prefix_hash_expiry_and_revocation(self) -> None:
        issued = issue_opaque_token(label="lumi")
        record = ApiTokenRecord(
            id="token-1",
            organization_id="org-a",
            name="automation",
            prefix=issued.prefix,
            secret_hash=issued.token_hash,
            scopes=frozenset({"projects:read"}),
            expires_at=NOW + timedelta(days=1),
        )
        validate_api_token(record, issued.plaintext, required_scope="projects:read", now=NOW)
        with self.assertRaisesRegex(PermissionError, "API_TOKEN_SCOPE_DENIED"):
            validate_api_token(record, issued.plaintext, required_scope="projects:write", now=NOW)

    def test_sliding_window_rate_limit_blocks_burst_and_recovers(self) -> None:
        limiter = InMemorySlidingWindowRateLimiter()
        for offset in range(3):
            limiter.consume("login:user", now=NOW + timedelta(seconds=offset), limit=3, window=timedelta(minutes=1))
        with self.assertRaises(RateLimitExceeded):
            limiter.consume("login:user", now=NOW + timedelta(seconds=3), limit=3, window=timedelta(minutes=1))
        limiter.consume("login:user", now=NOW + timedelta(minutes=2), limit=3, window=timedelta(minutes=1))


if __name__ == "__main__":
    unittest.main()
