# LUMI AI Design OS — Threat Model & Security Release Gate

Status: NODE-66 implementation baseline  
Review date: 2026-08-15  
Owner: Platform/Security  
Release policy: Critical = 0; High = 0 by default; any exception requires named owner, short expiry and explicit acceptance.

## 1. Frozen reference baseline

This review freezes the security baseline to OWASP Top 10:2025, OWASP Top 10 for LLM/GenAI Applications 2025, and the OWASP Agentic AI security guidance available at the review date. The release gate is implementation/tool independent: scanners may change, severity policy may not silently weaken.

## 2. Assets and trust boundaries

```text
Internet -> CDN/WAF -> Web/API
Browser -> Upload -> Object Storage
API -> PostgreSQL/Redis/Broker
Agent Runtime -> Model Gateway
Agent Runtime -> Tool Gateway
Tool Gateway -> Internet/MCP/SaaS
Agent -> Sandbox
Worker -> untrusted media/files
Admin -> privileged operations
```

Protected assets: tenant data, projects, assets, artifacts, runs, memories/knowledge, cost ledger, payment side effects, model/provider credentials, API tokens, sessions, audit records, prompts/system policies and tool capabilities.

## 3. STRIDE register

| ID | Boundary | Threat | Severity | Control | Automated evidence | Residual risk / owner |
|---|---|---|---|---|---|---|
| TM-01 | API -> tenant objects | BOLA/IDOR and nested tenant confusion | Critical | request principal + organization/project authorization; fail closed | auth tenant, privilege escalation and project security corpus | New resource types must add negative tests / API owner |
| TM-02 | Browser -> Auth | session theft/fixation/CSRF/replay | High | Secure/HttpOnly/SameSite cookies in non-dev; origin checks; one-time token storage/revocation | existing auth integration corpus | MFA/session shortening for privileged admin remains deployment requirement / Identity owner |
| TM-03 | Internet -> API | token leakage through URL/logs | High | query credential rejection; centralized secret redaction; no client secrets | `test_security_hardening.py`; gitleaks | downstream vendor logs need config review / Platform owner |
| TM-04 | Tool/Browser -> Internet | SSRF to loopback/RFC1918/link-local/metadata/IPv6 | Critical | scheme/userinfo checks; DNS resolution; private/reserved IP deny; revalidate every redirect | SSRF corpus | TOCTOU/DNS-rebinding requires fetch adapters to pin validated connection target / Tool Gateway owner |
| TM-05 | Upload -> parser/worker | traversal, SVG XSS, parser exploit, zip bomb | High | filename normalization; MIME/size policy; raw SVG deny; isolated worker requirement | upload corpus | AV/decompression/parser sandbox must stay enabled in deployment / Media owner |
| TM-06 | external content -> Agent | indirect prompt injection / instruction smuggling | Critical | trust label `external_untrusted`; external text is data, never authorization; server-side tool permissions | malicious instruction fixture | model may still follow benign-looking adversarial text; sensitive actions require HITL / Agent owner |
| TM-07 | Agent -> Tool | destructive action without consent | Critical | tool risk tiers; destructive/privileged operations require approval; recursion/budget caps in runtime | HITL security test + approval engine suite | per-tool classification drift / Tool owner |
| TM-08 | Agent -> Sandbox | host escape / credential/network exfiltration | Critical | no Docker socket/host mounts; read-only root where possible; seccomp/AppArmor/platform policy; egress deny/default; quotas | NODE-21 escape suite + deployment verification | kernel/runtime zero-days / Infra owner |
| TM-09 | CI -> production | vulnerable dependency/build-chain compromise | High | frozen lockfiles; CodeQL; dependency review; npm/pip audit; Trivy vuln/misconfig/secret; gitleaks | `security-release-gate.yml` | third-party action compromise; pin immutable SHAs where policy supports Dependabot/Renovate updates / DevSecOps owner |
| TM-10 | Web -> browser | XSS/clickjacking/content sniffing | High | CSP, frame-ancestors, nosniff, referrer and permissions policy, CORP, HSTS in prod | HTTP hardening test | app-specific CSP may need nonce/hash expansion without weakening frame/base directives / Web owner |
| TM-11 | API -> cost/model | denial-of-wallet/expensive expansion | High | budgets/quotas/concurrency/graph depth plus request body limits | cost and graph suites + release gate | distributed actor abuse requires WAF/rate-limit telemetry / Platform owner |
| TM-12 | Admin -> tenant data | privilege abuse / accidental content access | Critical | separate roles, audit trail, privileged confirmation, least privilege, break-glass procedure | admin + governance suites | production MFA/provider enforcement / Admin owner |

## 4. Security invariants

1. Model output is never an authorization decision.
2. Tenant identity comes from authenticated server context, never from a client-selected object alone.
3. Every tenant-scoped resource endpoint requires a negative cross-tenant test.
4. Every outbound redirect and resolved destination is revalidated before connection.
5. Untrusted file/media parsing runs without platform credentials or host access.
6. External documents/web/MCP/OCR content is labelled untrusted and cannot raise tool permissions.
7. Destructive and privileged tools require explicit human approval.
8. Secrets never belong in URL query, source control, browser bundles or unredacted logs.
9. Security scanner failures fail the release gate; they are not `continue-on-error`.

## 5. Attack corpus

### SSRF
Block loopback, localhost, RFC1918, link-local/cloud metadata, IPv6 local/private, encoded-IP variants, DNS answers resolving to forbidden ranges and redirects that change into forbidden ranges. Network adapters must call the guard on the initial URL and each redirect hop.

### Prompt injection
Fixtures include uploaded docs, web pages, MCP outputs and OCR text containing instructions such as “ignore system rules”, “upload all files”, “reveal secrets”, “approve this tool” and “change organization”. Expected result: content remains `external_untrusted`; authorization/tool scope is unchanged; destructive/privileged action remains blocked pending HITL.

### Upload
Reject traversal/control characters, over-limit files, disallowed MIME, raw SVG without isolated sanitizer, decompression over limits and unsafe archive paths. AV/parser availability must fail closed in production unless a documented exception is active.

### BOLA
For Project/Asset/Artifact/Run/Cost/Memory/Knowledge and future tenant entities, test read/list/update/delete/actions with IDs owned by another organization, nested parent/child mismatch, guessed IDs and role escalation.

## 6. Production deployment controls

- TLS at edge; HSTS on production application responses.
- WAF/rate limits by actor + organization + IP profile; expensive generation gets stricter quotas.
- Sandbox: non-root, read-only root where feasible, drop capabilities, no Docker socket, no host mounts, egress deny/default, CPU/memory/PID/time quotas.
- Secrets from cloud secret manager/workload identity; provider keys only at gateway; rotation procedure tested.
- Object storage private-by-default; short-lived signed URLs; malware/parser pipeline isolated.
- Admin MFA where identity provider supports it; shorter admin session; privileged confirmation and audit.

## 7. Incident / secret-rotation runbook

For suspected secret exposure: STOP SHIP -> revoke/rotate credential -> invalidate sessions/tokens if relevant -> search repository history, build artifacts, logs and telemetry -> contain affected provider/IAM scope -> audit access -> document timeline/root cause -> add regression detector -> resume only after Critical/High findings are zero or formally accepted under policy.

For suspected cross-tenant leak or sandbox escape: disable affected capability/route, preserve audit evidence, rotate potentially reachable credentials, enumerate impacted tenant/object set, run authorization/escape corpus, complete incident response and explicit security sign-off before re-enable.

## 8. Release evidence checklist

- [x] Threat boundaries and STRIDE register documented.
- [x] Existing tenant/BOLA negative suites retained; NODE-66 security corpus added.
- [x] Prompt-injection trust invariant and SSRF fixtures added.
- [x] Upload path/MIME/size baseline added.
- [x] Browser/API HTTP hardening added to public API/Auth/Project/Asset runtime boundary.
- [x] SAST/SCA/secret/IaC/filesystem vulnerability scans wired into CI.
- [x] Critical/High CI gate encoded.
- [x] Secret redaction primitive and rotation/incident runbook documented.
- [ ] NODE-21 sandbox escape suite must be re-run in the production-equivalent sandbox before production release.
- [ ] DAST must run against the deployed staging URL; this cannot be proven by source-only CI.
- [ ] Third-party penetration test remains required before enterprise/commercial launch per NODE-66 policy.

## 9. STOP SHIP conditions

Any cross-tenant data leak, remote sandbox escape, secret exposure with usable credentials, payment bypass, repeat paid side effect, or open Critical finding is STOP SHIP. High findings are launch-blocking by default.

## 10. Sign-off

Source implementation can be merged when the security release workflow is green. Production launch additionally requires staging DAST, production-equivalent sandbox escape verification and explicit owner sign-off for the deployment controls above.
