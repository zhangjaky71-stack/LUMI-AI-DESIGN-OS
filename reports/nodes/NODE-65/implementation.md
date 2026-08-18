# NODE-65 — Audit, Governance & Data Retention Implementation Report

Status: **CORE IMPLEMENTED / VALIDATING / NOT COMPLETE**  
Date: 2026-08-18  
Base: `feat/node-64-admin-console`

## 1. Implemented core

### Canonical organization Audit

- Existing `audit_events` is retained as the canonical organization Audit fact table rather than creating a third incompatible audit store.
- NODE-65 extends the fact with actor refs, resource version, result, reason code, request/trace IDs, security metadata, safe change summary, retention class/policy version and explicit `occurred_at`.
- Existing rows are normalized before stricter constraints are enabled:
  - legacy actor type is preserved in `details_json`;
  - canonical actor types are upper-cased/normalized;
  - missing actor IDs become `legacy:unknown`;
  - non-canonical legacy event hashes are preserved in `details_json` and replaced with a deterministic SHA-256 legacy hash.
- Database trigger rejects ordinary UPDATE/DELETE on `audit_events`.
- New writes maintain an organization-scoped SHA-256 chain (`previous_hash -> event_hash`).
- An organization-scoped PostgreSQL advisory transaction lock prevents concurrent writers from forking the hash-chain head.
- Cursor pagination supports time/actor/action/resource/result/trace filters while returning a safe summary projection rather than raw details/security metadata.

### Audit redaction

Before persistence NODE-65:

- replaces password/token/key/card/cookie/private-key fields with `[REDACTED]`;
- hashes prompts/raw content/message bodies instead of storing full content;
- strips query/fragment material from HTTP(S) URLs;
- hashes raw bytes;
- redacts secret-shaped free text such as Bearer tokens, OpenAI-style `sk-` values, GitHub tokens, AWS access-key IDs and JWT-shaped strings.

NODE-64 platform-admin reasons also reuse the free-text scrubber on this branch.

### Actor attribution

Canonical actor types:

- `USER`
- `API_TOKEN`
- `AGENT`
- `SERVICE`
- `PLATFORM_ADMIN`

Agent audit is fail-closed unless it has:

- agent/run identity;
- agent version;
- human initiator;
- no ambiguous `system` actor identity.

### Governance RBAC

Existing organization roles are reused, with narrower governance permissions:

- `ADMIN`: may read organization audit through `admin.audit.read` but cannot create/release Legal Hold, request deletion or export full audit.
- `OWNER`: additionally receives `governance.manage` and `audit.export`.
- API routes require a real human user actor for governance actions; an API token is not treated as an OWNER human principal merely because it carries scopes.

### Retention policies

Durable versioned policy rows exist for:

- `SECURITY_AUDIT`
- `BILLING`
- `CONTENT`
- `AGENT_TRACE`
- `TEMP_SANDBOX`
- `EXPORT`
- `ANALYTICS`

Migration defaults are explicitly labelled **technical baselines requiring legal review before jurisdictional launch**. They are not represented as legal advice or statutory requirements.

### Legal Hold

- Durable organization-scoped Hold rows.
- Supported scopes: ORGANIZATION / USER / PROJECT / ASSET / ARTIFACT / AUDIT.
- Create/release requires reason and `governance.manage`.
- Create/release generates a canonical governance Audit fact.
- Active organization-wide holds apply to every resource in that organization.
- Hold creation and deletion transition into ERASING share an organization-scoped advisory xact lock.
- ERASING SQL rechecks both originally recorded blockers and currently active Hold rows.

### Deletion workflow core

Implemented state/path contracts:

`IDENTIFIED -> DEACTIVATED -> ERASING -> COMPLETED|FAILED`

and

`HOLD_BLOCKED`

Execution requires three independently composed ports:

1. subject deactivation;
2. object deletion/GC;
3. search/vector reference deletion.

The service refuses deletion if any port is absent and refuses completion unless both object and search/vector propagation succeed. Production durable worker/crash recovery remains P0 and is not claimed complete.

### Audit export core

- Durable JSON/CSV export request record.
- `audit.export` permission separate from ordinary audit read.
- Export filters pass through redaction before durable storage.
- Missing export adapter fails before an orphan PENDING record is created.
- Export request itself emits an Audit event.
- Production export worker, signed result URL and download audit remain P0.

### API

Authenticated organization routes under `/api/v1/governance`:

- `GET /audit`
- `POST /legal-holds`
- `POST /legal-holds/{hold_id}/release`
- `POST /deletion-requests`
- `POST /audit-exports`

The request-scoped production `governance_service_factory` remains intentionally fail-closed until deployment composition is supplied.

## 2. Important non-claims

NODE-65 does **not** currently claim:

- all high-risk producers emit canonical Audit facts;
- production Deletion worker composition;
- production Retention sweeper/GC composition;
- production audit Export/download flow;
- global SECURITY_ADMIN unified query over organization + platform-admin audit sources;
- complete data-subject discovery/anonymization across every database/object/search/analytics surface;
- jurisdiction-specific legal retention correctness;
- hosted executed-green CI evidence.

These remain explicit P0/P1 entries in `reports/nodes/NODE-65/gap-ledger.json`.

## 3. Safety invariants

1. Audit facts are append-only at the database boundary.
2. Application API exposes no ordinary update/delete audit route.
3. Secret-bearing values are redacted/hashed before canonical Audit persistence.
4. Prompt/content bodies are references/hashes by default, not raw audit payloads.
5. Organization ADMIN read permission does not imply governance write/export permission.
6. Agent writes cannot be attributed to a vague `system` identity.
7. A Legal Hold blocks deletion even if the Hold appears after the deletion request was created.
8. A deletion cannot be declared complete unless deactivation, object GC and search/vector GC all run successfully.
9. Retention defaults are technical policy versions, not legal conclusions.
10. Missing production adapters fail closed.

## 4. Validation target

Dedicated NODE-65 CI must execute:

- Python compile;
- static NODE-65 acceptance validator;
- NODE-65 contract tests;
- API contract regression;
- Ruff;
- Pyright;
- full PostgreSQL migration chain through `20260818_0025`;
- durable table/constraint/trigger verification;
- direct UPDATE/DELETE rejection against `audit_events`;
- legacy audit normalization proof;
- canonical append/hash-chain proof;
- gap-ledger parse.

Hosted execution evidence is required before NODE-65 can leave NOT COMPLETE.
