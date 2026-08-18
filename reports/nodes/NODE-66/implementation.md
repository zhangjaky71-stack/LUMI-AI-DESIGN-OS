# NODE-66 — Security Hardening Implementation Report

Status: **CORE_IMPLEMENTED_VALIDATING_NOT_COMPLETE**  
Current stacked base: `feat/node-65-audit-governance`  
Current stacked head: `feat/node-66-security-hardening`

## 1. What this node implements

NODE-66 turns the existing per-component security controls into a release-oriented security baseline and adds missing application/browser policy primitives.

### New current-track implementation

- `lumi_api.security.http`
  - rejects credential/secret query parameter names;
  - bounds known-length JSON requests at the application layer;
  - emits API security headers;
  - adds HSTS only in production mode;
  - disables interactive Swagger/ReDoc/OpenAPI HTTP surfaces in production;
  - gives development API docs a separate CDN-limited CSP so strict API CSP does not break local documentation;
  - is composed in the real FastAPI app factory.
- `lumi_api.security.context`
  - explicit context trust classes;
  - external/web/tool/asset-extract context cannot become authoritative or grant authorization;
  - context stores a content SHA-256 rather than raw untrusted text;
  - secret-bearing source refs are rejected.
- `lumi_api.security.release_gate`
  - Critical always blocks;
  - High blocks by default;
  - optional High exception profile requires owner, reason and short expiry;
  - open Medium requires owner and due date.
- `apps/web/next.config.ts`
  - CSP baseline;
  - frame denial;
  - nosniff;
  - no-referrer;
  - Permissions-Policy;
  - COOP;
  - production HSTS;
  - development `connect-src` retains local HTTP/WS connectivity without weakening production CSP.
- `apps/api/tests/test_security_node66.py`
  - real FastAPI security composition;
  - production API-doc shutdown and development docs CSP;
  - credential-query rejection;
  - JSON body size limit;
  - trust boundary malicious content fixture;
  - release-gate policy;
  - web header contract.
- `docs/security/THREAT-MODEL.md`
  - frozen OWASP baseline;
  - trust boundaries;
  - threat register;
  - controls/evidence/residual risk;
  - STOP SHIP rules.
- NODE-66 dedicated security workflows
  - blocking pip-audit 2.10.1 against the frozen Python dependency export;
  - blocking Bandit 1.9.4 high-severity / medium-confidence Python SAST;
  - blocking `pnpm audit --audit-level high`;
  - blocking Trivy 0.36.0 filesystem vulnerability/secret/misconfiguration scan;
  - CycloneDX filesystem SBOM generation;
  - blocking CRITICAL/HIGH scan of the built Sandbox image;
  - separate guarded OWASP ZAP baseline workflow for configured HTTPS staging.

## 2. Existing security assets deliberately reused

### Tool Gateway / SSRF

Existing NODE-25 code already includes:

- `SSRFPolicy` public-IP enforcement;
- blocked localhost/private/link-local/metadata host classes;
- mixed public/private DNS fail-closed behavior;
- runtime DNS re-resolution;
- validated pinned IP handoff;
- SafeWebFetch redirect target revalidation;
- no ambient Authorization/Cookie forwarding;
- restricted content type and response size.

NODE-66 does not fork or replace this policy. It includes the existing tests in the release corpus and leaves production transport proof as an explicit P0.

### Sandbox

Existing NODE-21 local Docker backend already requires:

- `--network none`;
- `--read-only`;
- `--cap-drop ALL`;
- `no-new-privileges:true`;
- unprivileged UID/GID;
- PID/CPU/memory limits;
- readonly input bind;
- nosuid/nodev tmpfs work/output;
- no Docker socket;
- command allowlist and forbidden shell/network/admin executables;
- long-lived provider/database/cloud secret environment deny;
- workspace/archive traversal validation;
- bounded output and timeouts.

NODE-66 treats those source controls as closed core evidence but does not claim production escape resistance until the real runtime suite executes.

### Asset upload/storage

Existing Asset tests already cover:

- content magic-byte MIME sniffing;
- SVG script/event/external-resource/XXE rejection;
- filename sanitation;
- signed URL checksum binding and TTL cap.

Malware scanning, decompression-bomb limits and production parser isolation remain open.

### Supply chain

Repository-level pre-existing controls include:

- GitHub Dependency Review;
- CodeQL for Python and JavaScript/TypeScript when repository policy permits it;
- Gitleaks full-history secret scanning;
- frozen dependency lockfiles.

The existing Dependency Review workflow is intentionally not treated as sufficient release evidence because its native PR step is non-blocking when repository capability is unavailable. NODE-66 therefore adds its own blocking dependency/SAST/filesystem/image gates. Existing CodeQL/Gitleaks/Dependency Review YAML is still useful defense-in-depth, but neither YAML presence nor a skipped job is a green result.

## 3. Security boundaries kept fail-closed

- Security headers do not replace authorization or CSRF.
- Application request-size enforcement only claims known `Content-Length` JSON requests; chunked/streamed ingress remains P0.
- Context trust labels are not claimed end-to-end until production Agent context composition uses them.
- MCP transport `pinned_ip` is a required port contract; absence of a production adapter is a gap, not an implicit PASS.
- Local Docker Sandbox isolation flags are not a production escape-test result.
- Blocking pip-audit/Bandit/pnpm/Trivy/ZAP workflow definitions are not evidence that the latest head has passed them.
- CycloneDX generation is wired, but production image signing/attestation/provenance remains open.
- ZAP baseline is wired only to a repository-configured HTTPS staging URL; an unset variable means no DAST evidence.
- NODE-63/NODE-64/NODE-65 production gaps remain dependencies and are not closed by NODE-66 references.

## 4. Standards snapshot

Frozen on 2026-08-18 against official OWASP sources:

- OWASP Top 10:2025;
- OWASP ASVS 5.0.0;
- OWASP API Security Top 10:2023;
- OWASP Top 10 for LLMs / GenAI Applications 2025;
- OWASP Top 10 for Agentic Applications (December 2025 release).

The exact reference date/version is part of the threat model to avoid an unreviewed moving target.

## 5. Acceptance evidence staged

NODE-66 dedicated validation includes or stages:

- compile/static acceptance;
- new API security tests;
- existing Tool Gateway SSRF corpus;
- existing Sandbox security contract and archive/artifact limit tests;
- real Docker Sandbox attack/functional suite;
- existing Asset security contract;
- auth/API contract regressions;
- Web TypeScript/lint/build;
- dependency lock consistency;
- blocking Python/Node dependency audits;
- blocking Bandit high-severity SAST;
- blocking Trivy filesystem vuln/secret/misconfiguration scan;
- CycloneDX SBOM;
- blocking Sandbox image CRITICAL/HIGH scan;
- guarded staging ZAP baseline DAST workflow;
- checks that CodeQL, Dependency Review and Gitleaks workflows remain present;
- gap ledger fail-closed check.

## 6. Release blockers

Source of truth: `reports/nodes/NODE-66/gap-ledger.json`.

Current open P0 groups:

1. ingress/WAF streamed body/rate-limit/denial-of-wallet evidence;
2. complete maintained BOLA corpus;
3. end-to-end Agent trust-label/prompt-injection integration;
4. production pinned-IP Tool/MCP egress transport evidence;
5. production Sandbox escape/runtime policy evidence;
6. malware/decompression/parser-isolation evidence;
7. Secret Manager/workload identity/rotation;
8. latest-head execution of the new blocking scans plus complete production image signing/provenance and vulnerability-exception evidence;
9. Admin MFA/step-up/short privileged session dependency;
10. executed staging DAST plus authenticated/active DAST and independent penetration test;
11. NODE-65 production security/privileged Audit ingress;
12. latest-head hosted validation + named Security sign-off.

## 7. Explicit non-claims

This implementation does **not** currently claim:

- production-ready security sign-off;
- all Critical/High findings closed by executed scans;
- complete cross-tenant negative testing for every endpoint;
- production Sandbox escape resistance;
- production SSRF transport proof for every outbound client;
- fully deployed Agent prompt-injection trust propagation;
- executed staging DAST or third-party pentest completion;
- cloud Secret Manager/rotation deployment;
- full production image signing/attestation/provenance evidence;
- hosted CI green while GitHub Actions remains capable of pre-run failure.

NODE-66 remains **NOT COMPLETE** until the open P0 ledger is closed with executed evidence.
