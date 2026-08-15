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
Browser -> Upload -> Asset Storage -> Worker/Sandbox
API -> PostgreSQL/Redis/Broker
Agent Runtime -> Model Gateway
Agent Runtime -> Tool Gateway
Tool Gateway -> Internet/MCP/SaaS
Agent -> Sandbox
Admin -> privileged operations
```

Protected assets: tenant data, projects, assets, artifacts, runs, memories/knowledge, cost ledger, payment side effects, model/provider credentials, API tokens, sessions, audit records, prompts/system policies and tool capabilities.

## 3. Canonical security ownership

Security logic must have one authoritative owner per boundary. NODE-66 intentionally rejects parallel helper implementations that can drift.

| Boundary | Canonical owner | Security responsibility |
|---|---|---|
| Public HTTP perimeter | `apps/api` | request-size early guard, credential-in-query rejection, browser/API security headers, production HSTS, log redaction helper |
| Tenant authorization | Auth + Project Core/API security context | authenticated principal, organization/project boundary, role/permission checks, CSRF/session semantics |
| Outbound HTTP / SSRF | Tool Gateway | URL validation, DNS evaluation, private/metadata deny, validated-IP pinning, redirect revalidation, response limits, no ambient auth |
| Uploaded media | Asset Storage + isolated media workers | magic-byte MIME sniffing, declared/sniffed MIME agreement, SVG sanitization, object/storage policy |
| Archive/path execution | Sandbox Runtime | workspace path confinement, archive extraction safety, symlink/zip-slip rejection, network/resource policy |
| Retrieved/model context | Agent Context Engine | trust labels, instruction-authority separation, prompt-injection suspicion metadata, tenant-scoped retrieval |
| Sensitive actions | Project Core Approval + Tool Gateway/Agent approval bridge | explicit approval state, subject/version binding, tool authorization, idempotent execution |
| CI/release | Security workflows | SAST/SCA/secret/IaC/CodeQL/dependency review/security regression/DAST gates |

## 4. STRIDE register

| ID | Boundary | Threat | Severity | Control | Automated evidence | Residual risk / owner |
|---|---|---|---|---|---|---|
| TM-01 | API -> tenant objects | BOLA/IDOR and nested tenant confusion | Critical | request principal + organization/project authorization; fail closed | auth tenant, privilege-escalation and project-security corpus | New resource types must add negative tests / API owner |
| TM-02 | Browser -> Auth | session theft/fixation/CSRF/replay | High | Secure/HttpOnly/SameSite cookies in non-dev; origin checks; one-time token storage/revocation | auth integration corpus | MFA/session shortening for privileged admin remains deployment requirement / Identity owner |
| TM-03 | Internet -> API | token leakage through URL/logs | High | exact sensitive-query-key rejection; centralized redaction helper; no client secrets | `test_security_hardening.py`; gitleaks | downstream vendor logs need config review / Platform owner |
| TM-04 | Tool Gateway -> Internet | SSRF to loopback/RFC1918/link-local/metadata/IPv6; DNS rebinding/redirect pivot | Critical | `SSRFPolicy`; fail on mixed public/private DNS; validated-IP pinning; redirect revalidation; no ambient Authorization/Cookie | `services/tool-gateway/tests/test_ssrf.py` | transport adapters must preserve pinned-IP semantics / Tool Gateway owner |
| TM-05 | Upload -> parser/worker | MIME spoofing, SVG XSS/XXE/external fetch, traversal, zip slip/symlink, parser exploit | High | magic-byte sniffing + declared MIME agreement; SVG sanitizer; sandbox path/archive controls; isolated parser requirement | `services/asset-storage/tests/test_asset_storage_security.py`; sandbox contract corpus | AV/decompression/parser isolation remains deployment requirement / Media owner |
| TM-06 | external content -> Agent | indirect prompt injection / instruction smuggling | Critical | `UNTRUSTED_RETRIEVED_DATA`; `instruction_authority=none`; prompt-injection suspicion metadata; server-side permissions | `apps/agent-runtime/tests/test_context_engine.py` | model may still follow benign-looking adversarial text; sensitive actions remain approval-gated / Agent owner |
| TM-07 | Agent -> Tool | destructive action without consent or stale approval | Critical | canonical approval state + exact subject/version binding + Tool Gateway authorization/idempotency | approval bridge + approval engine + tool gateway suites | per-tool risk/permission classification drift / Tool owner |
| TM-08 | Agent -> Sandbox | host escape / credential or network exfiltration | Critical | network NONE by default; allowlist validation; path confinement; quotas; no host/Docker-socket exposure in production profile | sandbox contract corpus + production-equivalent escape verification | kernel/runtime zero-days / Infra owner |
| TM-09 | CI -> production | vulnerable dependency/build-chain compromise | High | frozen lockfiles; CodeQL; dependency review; npm/pip audit; Trivy vuln/misconfig/secret; gitleaks; high-severity Bandit across apps/services/packages | `security-release-gate.yml` | third-party action compromise; immutable SHA pinning can further reduce risk / DevSecOps owner |
| TM-10 | Web/API -> browser | XSS/clickjacking/content sniffing | High | CSP/frame-ancestors, X-Frame-Options, nosniff, referrer/permissions policy, CORP, HSTS in prod | HTTP hardening test | app-specific CSP may require nonce/hash expansion without weakening frame/base directives / Web owner |
| TM-11 | API -> cost/model | denial-of-wallet/expensive expansion | High | budgets/quotas/concurrency/graph depth plus ingress/application body limits | cost and graph suites + release gate | distributed actor abuse requires WAF/rate-limit telemetry / Platform owner |
| TM-12 | Admin -> tenant data | privilege abuse / accidental content access | Critical | separate roles, audit trail, privileged confirmation, least privilege, break-glass procedure | admin + governance suites | production MFA/provider enforcement / Admin owner |

## 5. Security invariants

1. Model output is never an authorization decision.
2. Tenant identity comes from authenticated server context, never from a client-selected object alone.
3. Every tenant-scoped resource endpoint requires a negative cross-tenant test.
4. Outbound HTTP is performed through Tool Gateway policy; every redirect/destination is revalidated and the validated IP is pinned into transport.
5. Untrusted file/media parsing runs without platform credentials or host access.
6. External documents/web/MCP/OCR content is untrusted data and cannot raise instruction authority or tool permissions.
7. Destructive and privileged operations require canonical authorization/approval; approval is bound to the exact subject/version where applicable.
8. Secrets never belong in URL query, source control, browser bundles or unredacted logs.
9. Security scanner failures fail the release gate; security jobs may not use `continue-on-error` to bypass Critical/High findings.
10. Application `Content-Length` checks are defense-in-depth only; production ingress must enforce a real body-size ceiling for streamed/chunked requests.

## 6. Attack corpus

### SSRF
Block loopback, localhost, RFC1918, link-local/cloud metadata, IPv6 local/private, mixed public/private DNS answers and redirects that pivot to forbidden ranges. Tool Gateway must preserve the validated/pinned IP through transport and strip ambient Authorization/Cookie state.

### Prompt injection
Fixtures include retrieved web/research content containing instructions such as “ignore previous instructions” or “reveal the system prompt”. Expected result: the item remains `UNTRUSTED_RETRIEVED_DATA`, has `instruction_authority=none`, is marked suspicious where patterns match, and does not modify authorization/tool scope.

### Upload/media
Treat declared MIME as untrusted. Sniff magic bytes, require declared/sniffed agreement, reject arbitrary HTML masquerading as media, and sanitize SVG by rejecting scripts, event handlers, DTD/entities and external/dangerous references. Archive/path processing must reject traversal and symlinks.

### BOLA
For Project/Asset/Artifact/Run/Cost/Memory/Knowledge and future tenant entities, test read/list/update/delete/actions with IDs owned by another organization, nested parent/child mismatch, guessed IDs and role escalation.

## 7. Production deployment controls

- TLS at edge; HSTS on production application responses.
- Ingress/proxy request-body limit at or below the application limit; do not rely on `Content-Length` alone.
- WAF/rate limits by actor + organization + IP profile; expensive generation gets stricter quotas.
- Sandbox: non-root, read-only root where feasible, drop capabilities, no Docker socket, no host mounts, egress deny/default, CPU/memory/PID/time quotas.
- Secrets from cloud secret manager/workload identity; provider keys only at gateway; rotation procedure tested.
- Object storage private-by-default; short-lived signed URLs; malware/parser pipeline isolated.
- Admin MFA where identity provider supports it; shorter admin session; privileged confirmation and audit.

## 8. Security automation

### Source/repository release gate
`.github/workflows/security-release-gate.yml` runs the canonical authorization, Tool Gateway SSRF/error-sanitization, Sandbox, Agent Context/approval, Asset Storage MIME/SVG, SAST/SCA, dependency-review, CodeQL, secret and IaC/filesystem vulnerability gates. Critical/High findings block release.

### Staging DAST
`.github/workflows/security-dast.yml` is a manual/reusable OWASP ZAP baseline workflow. Before scanning it validates that the supplied target is an absolute public HTTPS target and rejects local/private/link-local/reserved destinations, preventing the CI scanner itself from becoming an internal-network probe. DAST evidence is only valid after the workflow has executed against the deployed staging environment.

## 9. Incident / secret-rotation runbook

For suspected secret exposure: STOP SHIP -> revoke/rotate credential -> invalidate sessions/tokens if relevant -> search repository history, build artifacts, logs and telemetry -> contain affected provider/IAM scope -> audit access -> document timeline/root cause -> add regression detector -> resume only after Critical/High findings are zero or formally accepted under policy.

For suspected cross-tenant leak or sandbox escape: disable affected capability/route, preserve audit evidence, rotate potentially reachable credentials, enumerate impacted tenant/object set, run authorization/escape corpus, complete incident response and explicit security sign-off before re-enable.

## 10. Release evidence checklist

- [x] Threat boundaries and STRIDE register documented.
- [x] Canonical security ownership mapped; duplicate NODE-66 SSRF/upload/prompt/tool-approval helpers removed from API perimeter.
- [x] Existing tenant/BOLA negative suites retained and wired into the security release gate.
- [x] Canonical Tool Gateway SSRF regression corpus wired into the release gate.
- [x] Canonical Agent Context prompt-injection/trust corpus wired into the release gate.
- [x] Sandbox path/archive/network/redaction corpus wired into the release gate.
- [x] Asset Storage MIME spoofing and SVG active-content security corpus added.
- [x] Browser/API HTTP perimeter hardening added to public API/Auth/Project runtime boundaries.
- [x] SAST/SCA/secret/IaC/filesystem vulnerability scans wired into CI; Bandit covers apps/services/packages at High severity.
- [x] Critical/High CI gate encoded.
- [x] Guarded staging DAST workflow added.
- [x] Secret redaction primitive and rotation/incident runbook documented.
- [ ] Security Release Gate must execute successfully after GitHub Actions runner billing/spending-limit access is restored.
- [ ] NODE-21 sandbox escape suite must be re-run in the production-equivalent sandbox before production release.
- [ ] DAST workflow must run successfully against the deployed staging URL.
- [ ] Third-party penetration test remains required before enterprise/commercial launch per NODE-66 policy.

## 11. Current validation status — 2026-08-15

The PR source is not security-signed-off yet. GitHub created the expected workflow runs, but the jobs did not start: the check annotation states that recent account payments failed or the Actions spending limit needs to be increased. The failed jobs therefore have no executed test steps and cannot be treated as product/security failures or successes.

This external Actions-account blocker must be cleared, then the latest PR head must be re-run through `Security Release Gate`. Until that happens the PR remains Draft and NODE-66 remains RELEASE BLOCKED.

## 12. STOP SHIP conditions

Any cross-tenant data leak, remote sandbox escape, secret exposure with usable credentials, payment bypass, repeat paid side effect, or open Critical finding is STOP SHIP. High findings are launch-blocking by default.

## 13. Sign-off

Source implementation can be marked ready for review only when the Security Release Gate executes and is green. Production launch additionally requires staging DAST, production-equivalent sandbox escape verification, deployment-control sign-off and the required independent penetration test.
