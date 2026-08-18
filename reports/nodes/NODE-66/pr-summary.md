# NODE-66 Current-Track PR Summary

Use this file as the durable source for the current stacked PR description.

## Implemented core

- frozen 2026-08-18 OWASP security baseline and TM-01..TM-17 threat register;
- authoritative FastAPI response hardening, credential-query rejection, known-length JSON request cap, production HSTS and production API-doc shutdown;
- Next.js CSP/frame/referrer/nosniff/permissions/COOP + production HSTS baseline;
- trust-labelled Agent context envelope where external/tool/asset content cannot authorize and raw content/secrets cannot hide in metadata;
- fail-closed Critical/High SecurityReleaseGate with bounded, explicit High exception profile;
- machine-readable BOLA corpus with VERIFIED/PARTIAL/MISSING evidence instead of field-presence claims;
- reuse of existing Tool Gateway SSRF, Sandbox isolation and Asset parser security corpora without forking those truth layers;
- blocking current-track pip-audit/Bandit/pnpm/Trivy filesystem and Sandbox-image scanning plus CycloneDX SBOM wiring;
- guarded blocking OWASP ZAP baseline workflow for a configured HTTPS staging target;
- static anti-downgrade gate, dedicated NODE-66 CI, explicit residual-risk gap ledger.

## Current non-complete gates

- full two-tenant BOLA matrix across every resource family;
- production Agent trust-label propagation and malicious-content E2E;
- production pinned-IP Browser/Tool/MCP transport proof;
- production-equivalent Sandbox runtime escape/security evidence;
- malware/decompression/parser-isolation evidence;
- Secret Manager/workload identity/rotation;
- all production image provenance/signing and executed scan results;
- NODE-64 privileged identity/MFA/step-up/session/dual-control dependencies;
- executed staging/authenticated DAST and independent penetration test;
- NODE-65 production security/privileged Audit ingress;
- latest-head hosted CI and named Security sign-off.

Status remains `CORE_IMPLEMENTED_VALIDATING_NOT_COMPLETE`.
