# NODE-65 — Audit, Governance & Data Retention Acceptance

Status: **IMPLEMENTED / VALIDATING / NOT COMPLETE**

## Implementation evidence

- append-only `AuditEvent` domain with organization-scoped hash chaining;
- correction-by-new-event only; no ordinary Audit update/delete API;
- USER / PLATFORM_ADMIN / AGENT / SERVICE actor identity;
- Agent audit fails closed without exact agent version + Run + Task + human initiator;
- organization audit query forced to its tenant; Platform Security cross-org is a separate permission path;
- cursor pagination and time/actor/action/resource/result/trace filters;
- field-level redaction for secrets, credentials, card values, prompt/content, IP and presigned URL query material;
- bounded safe change summary with changed fields, version refs and semantic diff ref;
- seven explicit versioned Retention classes;
- event-sourced Legal/Billing Hold create/release;
- retention candidates exclude active holds;
- event-sourced deletion workflow with hold blocking, deactivate, delete/anonymize, object GC, search/vector removal and completion counts;
- `RETENTION_ONLY` resources remain retained by deletion workflow;
- async JSON/CSV audit exports with immutable object ref/checksum/size;
- READY-only 30–900 second signed download leases; signed URLs are not persisted;
- NODE-64 `AdminAuditSink` adapter into canonical NODE-65 audit;
- organization Governance Center at `/app/settings/governance`;
- PostgreSQL migration 0014 with append-only mutation triggers + privilege revocation;
- no package.json / pnpm-lock / uv.lock change required.

## Validation staged

- domain append-only/hash/correction tests;
- redaction and Agent identity tests;
- tenant-scope and Platform Security tests;
- NODE-64 Admin sink integration tests;
- retention version/candidate tests;
- Legal Hold / deletion / GC/search propagation tests;
- audit export lifecycle + fresh signed lease tests;
- FastAPI governance router tests;
- web contract/gateway tests;
- browser E2E/mobile;
- PostgreSQL append-only schema gate;
- prior NODE-64 through NODE-54 regressions.

These suites are **STAGED**, not observed PASS, until hosted runners actually execute them.

## Explicit production integration gates

- [ ] production PostgreSQL `GovernanceRepository` adapter bound to migration 0014;
- [ ] NODE-16 auth/session/token/membership event producers bound;
- [ ] NODE-25 Tool Gateway write/destructive/privileged audit producers bound;
- [ ] Artifact/Asset/Brand/Approval/Billing producers bound;
- [ ] real object GC adapter bound;
- [ ] real search/vector deletion adapter bound;
- [ ] background retention/deletion/export workers deployed;
- [ ] production Platform Security actor resolver + organization governance permission resolver deployed;
- [ ] external WORM/KMS/storage-retention policy enabled where required;
- [ ] applicable legal/contractual retention + data-subject policy reviewed before launch;
- [ ] hosted pinned validation observed green.

The deterministic repository, resource adapters, browser fixture and in-memory export object store are engineering evidence only. They are not represented as deployed durable governance infrastructure.

## Definition of Done

- [x] canonical Audit pipeline/domain implemented;
- [x] append-only DB contract implemented;
- [x] redaction / actor / tenant guardrails implemented;
- [x] retention classes + policy versioning implemented;
- [x] Legal Hold path implemented;
- [x] deletion workflow path implemented;
- [x] audit export path implemented;
- [x] NODE-64 Admin audit bridge implemented;
- [x] Governance Center implemented;
- [x] tests and CI gates staged;
- [ ] production adapters/workers deployed;
- [ ] legal/contractual policy review complete;
- [ ] hosted pinned validation observed green.

Hosted evidence will be appended after the implementation commit triggers GitHub Actions.
