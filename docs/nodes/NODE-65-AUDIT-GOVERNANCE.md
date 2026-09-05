# NODE-65 — Audit, Governance & Data Retention

> Phase: 8 SaaS & Collaboration  
> Status: **IMPLEMENTED / VALIDATING / NOT COMPLETE**  
> Priority: P0/P1 SECURITY & ENTERPRISE  
> Depends on: NODE-10, NODE-16, NODE-25, NODE-42, NODE-62, NODE-64  
> Produces: Append-only Audit、Retention、数据删除/Legal Hold、审计导出与治理规则

---

## 1. Implementation baseline

NODE-65 establishes a governance plane rather than another application-log viewer.

Canonical layers:

```text
AuditEvent                append-only
RetentionPolicy           immutable + versioned
LegalHoldEvent            append-only CREATE / RELEASE
DeletionEvent             append-only workflow history
AuditExportJob            controlled async lifecycle
```

Product route: `/app/settings/governance`.

The organization surface is tenant scoped. Broader Platform Security access is a separate principal/permission path and must not be inferred from tenant `OWNER` / `ADMIN` alone.

## 2. Audit Event

Canonical V1 contains:

```text
event_id
organization_id?
actor_type USER / PLATFORM_ADMIN / AGENT / SERVICE
actor_id + actor_version?
session_ref / api_token_ref / agent_run_ref / task_ref
human_initiator_id?
action
resource_type / resource_id / resource_version?
result SUCCESS / DENIED / FAILED
reason_code
request_id / trace_id
safe security metadata
safe change summary
retention_class + retention_policy_version
correction_of_event_id?
occurred_at
prev_hash / event_hash
```

Audit is append-only. Ordinary application code has no Update/Delete Audit method. Corrections create a new `AUDIT_CORRECTION` record.

Migration `0014_audit_governance.sql` reinforces this with UPDATE/DELETE rejection triggers and privilege revocation for Audit, Retention policy, Legal Hold event and Deletion event tables.

## 3. Required producers

The canonical sink is designed for:

- auth/login/session/token events from NODE-16;
- membership/role changes;
- project delete/archive;
- sensitive Asset downloads/deletes;
- Brand Rule publish;
- Artifact approval/restore;
- constraint override;
- external write/destructive/privileged tools from NODE-25;
- Billing/Credit actions;
- Admin actions from NODE-64;
- provider/registry config;
- DLQ replay;
- secret/config access where the platform supports it.

NODE-65 implements the sink, schema and NODE-64 adapter. Other producers remain explicit integration gates until their production runtime adapters are connected.

## 4. Change summary

Audit does not persist full large before/after payloads by default.

```text
changed_fields[]
version_refs[]
semantic_diff_ref?
evidence_ref?
```

Fields and refs are bounded. Raw prompts/user content default to hash/ref.

## 5. Redaction

Forbidden Audit material includes:

- passwords;
- raw API keys/client secrets;
- session secrets;
- full Authorization credentials;
- payment-card PAN/CVC/CVV;
- full presigned URL query strings;
- raw prompt/content bodies unless a separately governed immutable evidence store is explicitly used.

Current V1 metadata sanitizer redacts credential-key fields, hashes prompt/content and IP-like fields, strips sensitive URL query material and bounds values.

## 6. Agent identity

Agent audit must include:

```text
agent id
exact agent version
AgentRun
Task
human initiator
```

An `AGENT` actor missing any required identity fails closed with `GOVERNANCE_AGENT_IDENTITY_INCOMPLETE`. Tool writes and constraint overrides therefore cannot be attributed to a vague `system` actor.

## 7. Tenant boundary

Organization callers require `audit.read` and are forced to their own `organization_id` regardless of requested filter.

Cross-organization Audit is allowed only to a separate Platform Admin actor carrying `admin.audit.read`. This does not derive from tenant role names.

Search filters:

```text
time
actor
action
resource type/id
result
organization (platform scope only)
trace id
```

Pagination uses an opaque cursor built from `(occurred_at,event_id)`, not a mutable numeric offset.

## 8. Retention classes

Exactly seven classes are implemented:

```text
SECURITY_AUDIT
BILLING
CONTENT
AGENT_TRACE
TEMP_SANDBOX
EXPORT
ANALYTICS
```

Each class has an immutable policy version and explicit retention days. A policy change appends the next version; historical Audit Events retain the exact policy version that applied when recorded.

The seeded v1 durations are **engineering defaults, not legal advice or a compliance claim**. Applicable laws, regulations and contracts must be reviewed before production launch.

Retention candidate computation excludes any resource matched by an active Legal/Billing Hold.

## 9. Legal / Billing Hold

Hold create/release are append-only events and require high governance permission plus reason/ticket.

Scopes:

```text
USER
ORGANIZATION
RESOURCE
RETENTION_CLASS
```

An active hold blocks affected GC and deletion execution. Release never rewrites the creation record; it appends a `RELEASE` event and Audit event.

## 10. Data deletion workflow

Implemented orchestration:

```text
identify subject scope
→ Legal/Billing Hold check
→ deactivate subject
→ DELETE / ANONYMIZE eligible resources
→ object storage GC
→ search/vector ref removal
→ retain RETENTION_ONLY evidence
→ append completion/failure event
```

Deletion is idempotently addressed by `request_id`. `BLOCKED_HOLD` is an explicit state. Completion exposes deleted/anonymized/retained counts.

NODE-65 does not delete its own Audit trail as part of ordinary user deletion. Security/Billing evidence can remain under policy/hold.

## 11. Audit export

Formats: JSON / CSV.

Flow:

```text
PENDING
→ RUNNING
→ immutable export object ref/checksum/size
→ READY
→ short-lived signed download lease
```

Signed URL is never persisted in `governance_audit_export_jobs`. Download TTL is 30–900 seconds. Refreshing a signed lease does not rerender the export job. V1 export is bounded to 50,000 audit events.

Every export request, ready transition and download is itself audited.

## 12. NODE-64 integration

`Node64AdminAuditSink` adapts NODE-64 `AdminAuditEvent` into canonical NODE-65 Audit.

The adapter:

- preserves actor/action/target identity;
- maps organization scope when safely known;
- hashes free-form admin reason instead of copying it;
- carries safe ticket/metadata projection;
- supports NODE-64 recent Admin Audit projection from canonical `ADMIN_*` events.

This closes NODE-64's durable Audit contract boundary at the domain level; production database binding remains an integration gate.

## 13. Product UX

`/app/settings/governance` provides:

- Audit search/filter/readout;
- explicit tenant scope;
- Retention policy versions and eligible candidates;
- active Legal Holds and guarded hold workflow;
- Deletion requests with hold-block and completion counts;
- Audit Export jobs and fresh signed lease retrieval;
- mobile layout;
- explicit truth boundaries around legal review and retained evidence.

The browser has no Audit database and uses no localStorage/sessionStorage/IndexedDB as canonical governance state.

## 14. Tests staged

Backend/domain:

- append-only + hash chain;
- correction adds event instead of mutation;
- credential/prompt/URL redaction;
- tenant separation and Platform Security access;
- Agent exact identity;
- NODE-64 Admin sink;
- versioned Retention;
- Legal Hold blocking retention/deletion;
- object GC + search/vector removal;
- retained evidence;
- async export + READY-only fresh signed lease.

API:

- tenant Audit route;
- cross-tenant denial;
- privileged Retention/Hold/Deletion;
- correction;
- Export worker and download lifecycle.

Web:

- contract/gateway units;
- browser Audit filter;
- all seven Retention classes;
- Hold → blocked deletion → release → completed deletion;
- signed lease refresh without rerender;
- mobile.

Database:

- migration applies on PostgreSQL 17;
- seven default Retention policies exist;
- append-only trigger rejects Audit UPDATE/DELETE;
- no signed URL or credential-bearing columns.

## 15. Production integration gates

NODE-65 is **NOT COMPLETE** until:

1. production PostgreSQL `GovernanceRepository` adapter is bound;
2. NODE-16 auth/request event producers emit to canonical Audit;
3. NODE-25 Tool Gateway write/destructive/privileged producers emit;
4. Artifact/Asset/Brand/Approval/Billing producers emit;
5. production object GC and search/vector removal adapters are connected;
6. background Retention/Deletion/Export workers are deployed;
7. production Platform Security and organization governance permission resolvers are bound;
8. external WORM/KMS/storage-retention controls are enabled where required;
9. applicable legal/contractual retention and data-subject rules receive jurisdiction-specific review;
10. hosted pinned validation executes green.

## 16. Definition of Done

```text
audit pipeline implemented
+ append-only DB contract implemented
+ governance services implemented
+ redaction/retention/hold/deletion/export tests staged
+ production adapters/workers connected
+ hosted gates green
```

Current status: **IMPLEMENTED / VALIDATING / NOT COMPLETE**.

下一节点：**NODE-66 — Security Hardening**。
