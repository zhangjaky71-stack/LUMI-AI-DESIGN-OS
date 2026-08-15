# NODE-66 — Security Hardening Release Evidence

Status: **RELEASE BLOCKED**  
Date: 2026-08-15  
PR: #66 — `NODE-66: Security hardening and threat model`  
Branch: `node-66-security-hardening-release`

## 1. Decision

NODE-66 source implementation is substantially in place, but it is **not signed off**. The pull request must remain Draft until executable security evidence is available.

The current GitHub Actions failures are infrastructure/account failures, not executed test failures: GitHub reports that jobs were not started because recent account payments failed or the Actions spending limit needs to be increased. Jobs therefore have no test steps and provide neither PASS nor FAIL evidence for the product code.

## 2. Implemented source controls

| Area | Canonical implementation/evidence | Source status | Executed status |
|---|---|---:|---:|
| HTTP perimeter | `apps/api/src/lumi_api/security/hardening.py` | DONE | BLOCKED BY ACTIONS |
| Auth/tenant isolation | existing auth + project security suites | DONE | BLOCKED BY ACTIONS |
| SSRF | Tool Gateway `SSRFPolicy` + safe fetch adapter | DONE | BLOCKED BY ACTIONS |
| Prompt injection | Agent Context Engine trust/instruction boundary | DONE | BLOCKED BY ACTIONS |
| Sensitive approval | Project Core Approval + Agent approval bridge + Tool Gateway | EXISTING/CANONICAL | BLOCKED BY ACTIONS |
| Sandbox path/network/archive controls | Sandbox Runtime | EXISTING/CANONICAL | BLOCKED BY ACTIONS |
| Upload MIME/SVG safety | Asset Storage sniff/sanitizer + NODE-66 regression tests | DONE | BLOCKED BY ACTIONS |
| Secret scan | Gitleaks using repository `.gitleaks.toml` | WIRED | BLOCKED BY ACTIONS |
| Python SAST | Bandit High severity over `apps services packages` | WIRED | BLOCKED BY ACTIONS |
| Dependency/SCA | pip-audit + pnpm audit + dependency review | WIRED | BLOCKED BY ACTIONS |
| IaC/filesystem vuln scan | Trivy Critical/High | WIRED | BLOCKED BY ACTIONS |
| CodeQL | private-repo policy: run when `LUMI_ENABLE_CODEQL=1` | WIRED/CONDITIONAL | NOT EXECUTED |
| Staging DAST | guarded OWASP ZAP baseline workflow | WIRED | NOT EXECUTED |

## 3. Security regression corpus frozen by NODE-66

The Security Release Gate must execute at minimum:

- `apps/api/tests/test_security_hardening.py`
- `apps/api/tests/integration/test_auth_tenant.py`
- `apps/api/tests/integration/test_auth_privilege_escalation.py`
- `apps/api/tests/integration/test_project_security.py`
- `services/tool-gateway/tests/test_ssrf.py`
- `services/tool-gateway/tests/test_mcp_error_sanitization.py`
- `services/sandbox-runtime/tests/test_sandbox_contracts.py`
- `apps/agent-runtime/tests/test_context_engine.py`
- `apps/agent-runtime/tests/test_approval_bridge.py`
- `services/asset-storage/tests/test_asset_storage_security.py`

These tests deliberately bind NODE-66 to the existing canonical security owners instead of introducing duplicate SSRF/upload/prompt/approval implementations in the API layer.

## 4. Current external blocker

GitHub Actions cannot currently allocate a runner for this repository. The check annotation on the latest NODE-66 PR head states:

> The job was not started because recent account payments have failed or your spending limit needs to be increased.

Required repository/account action: resolve GitHub Billing / Actions spending-limit access, then re-run the latest PR checks. No code change can correctly convert this infrastructure failure into valid test evidence.

## 5. Private repository CodeQL policy

The repository is private. Existing repository policy already runs CodeQL only when the repository is public or `LUMI_ENABLE_CODEQL=1`. NODE-66 reuses that policy rather than inventing a conflicting rule.

For source PR gating, CodeQL may be skipped by that explicit private-repository policy while the other SAST/SCA/security gates remain mandatory. **Production security sign-off must record either:**

1. CodeQL enabled and green (`LUMI_ENABLE_CODEQL=1` with required GitHub entitlement/configuration), or
2. a named, approved equivalent SAST control with Critical/High findings at zero.

A silent scanner skip is not acceptable production evidence.

## 6. Staging DAST gate

`.github/workflows/security-dast.yml` accepts a staging `target_url` through `workflow_dispatch` or `workflow_call`.

Before ZAP runs, the workflow requires an absolute HTTPS URL, rejects URL userinfo, resolves the hostname, and rejects local/private/link-local/reserved/multicast/unspecified destinations. This prevents the DAST workflow from being used as an internal-network probe.

Production evidence requires a successful run against the actual deployed staging URL. Source presence alone is not DAST evidence.

## 7. Remaining production blockers

- [ ] Restore GitHub Actions runner access and obtain a green `Security Release Gate` on the latest PR head.
- [ ] Resolve any real failures revealed after runners can start; do not waive Critical/High findings by changing thresholds.
- [ ] Enable CodeQL or document an approved equivalent SAST control for production sign-off.
- [ ] Run the production-equivalent NODE-21 sandbox escape/security verification.
- [ ] Run `Security DAST` against the deployed staging HTTPS URL and retain the report artifact.
- [ ] Verify production ingress body-size limits for streamed/chunked uploads, not only application `Content-Length` checks.
- [ ] Verify production secret-manager/workload-identity configuration and perform a rotation exercise.
- [ ] Verify admin MFA/session policy and privileged/break-glass audit controls.
- [ ] Complete the required independent penetration test before enterprise/commercial launch.
- [ ] Obtain named Platform/Security sign-off.

## 8. STOP SHIP

The release remains blocked for any open Critical finding, cross-tenant data exposure, remote sandbox escape, usable secret exposure, payment bypass/repeated paid side effect, or unresolved High finding without an explicit short-lived exception permitted by policy.

## 9. Transition rule

Only after the executable gates above are satisfied may PR #66 move from Draft to Ready for Review. NODE-66 may be marked complete only after the release evidence is updated with the successful run identifiers and the remaining production-only controls have named owners/status.
