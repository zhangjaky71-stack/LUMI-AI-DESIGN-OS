# Audit & Governance Runtime V1

Status: **IMPLEMENTED / VALIDATING / NOT COMPLETE**

## Canonical truth

NODE-65 separates operational logs from governance truth.

- `AuditEvent` is append-only and queryable.
- `RetentionPolicy` is immutable and versioned.
- Legal Hold is event-sourced (`CREATE` / `RELEASE`).
- Deletion is event-sourced (`REQUESTED` → hold check → deactivate → delete/anonymize → GC/search removal → terminal result).
- Audit Export is an asynchronous mutable job; the rendered export object is immutable by ref/checksum.
- Signed download URLs are response-only leases and are never canonical state.

## Actor identity

Audit actors are `USER`, `PLATFORM_ADMIN`, `AGENT`, or `SERVICE`.

Agent events fail closed unless exact agent version, AgentRun, Task and human initiator are present. Tool writes and constraint overrides therefore cannot be attributed to a vague `system` actor.

## Tenant scope

Organization actors require `audit.read` and are always forced to their current `organization_id`. A caller cannot make an organization audit query cross tenant by supplying another organization id.

Platform security access is a separate principal path and requires `PLATFORM_ADMIN` plus `admin.audit.read` for cross-organization audit projection.

## Append-only behavior

The normal domain API has no update/delete Audit method. Corrections create a new `AUDIT_CORRECTION` event with `correction_of_event_id`.

Migration `0014_audit_governance.sql` adds database triggers rejecting UPDATE/DELETE for:

- `audit_events`
- `governance_retention_policies`
- `governance_legal_hold_events`
- `governance_deletion_events`

It also revokes UPDATE/DELETE on those tables from `PUBLIC`.

V1 additionally stores an organization-scoped SHA-256 predecessor hash and event hash so accidental/tampering changes can be detected. This is not represented as external WORM storage.

## Audit redaction

Audit metadata is an allowlisted/sanitized projection. It must not persist:

- passwords;
- raw API keys/client secrets;
- session secrets;
- full Authorization credentials;
- payment-card PAN/CVC/CVV;
- full presigned URL query strings;
- raw prompts or user-content bodies by default.

Prompt/content fields are represented by hashes or immutable evidence refs. IP-like security values are hashed in the current V1 projection. Large before/after values are replaced with changed fields, exact version refs and optional semantic diff ref.

## Retention classes

The V1 schema requires exactly these governance classes:

- `SECURITY_AUDIT`
- `BILLING`
- `CONTENT`
- `AGENT_TRACE`
- `TEMP_SANDBOX`
- `EXPORT`
- `ANALYTICS`

The seeded v1 day counts are **engineering defaults only**. They are not legal advice or claims of compliance in any jurisdiction. Applicable legal, contractual and regulatory requirements must be reviewed before production launch. Changes publish a new immutable policy version.

Retention candidate computation uses the current exact policy version and excludes resources covered by an active Legal/Billing Hold.

## Legal Hold

A hold is created and released by append-only events. A hold may scope:

- User
- Organization
- Resource
- Retention class

Create/release requires a high-permission governance actor and records reason code + ticket reference. Active holds block affected retention GC and deletion execution.

## Data deletion

Deletion does not mean deleting every row indiscriminately.

```text
identify subject scope
→ active Legal/Billing Hold check
→ deactivate subject
→ DELETE / ANONYMIZE eligible resources
→ object-store GC
→ search/vector reference removal
→ retain policy-required evidence
→ append completion event
```

Resources can declare `DELETE`, `ANONYMIZE`, or `RETENTION_ONLY`. Security Audit/Billing evidence may remain retained when policy/hold requires it. NODE-65 never deletes its own audit trail as part of a normal subject-deletion workflow.

Production launch requires legal review of data-subject rights, statutory retention, contractual retention, backup semantics and jurisdiction-specific obligations.

## Audit export

JSON and CSV are supported.

Large export flow:

```text
create PENDING job
→ worker RUNNING
→ render bounded query
→ immutable object ref + checksum + size
→ READY
→ create short-lived signed download lease
```

V1 caps one export at 50,000 audit records. Signed download lease TTL is 30–900 seconds. Refreshing a lease does not rerender or create a new export job.

## NODE-64 integration

`Node64AdminAuditSink` adapts NODE-64 privileged `AdminAuditEvent` writes into the canonical NODE-65 audit pipeline. Raw free-form support reason is not copied into the audit record; the sink persists a reason hash and safe ticket/metadata projection.

The NODE-64 Admin Console `recent()` projection can read canonical `ADMIN_*` events back through this adapter.

## Production integration gates

The following remain explicit deployment integrations rather than deterministic evidence:

1. durable production `GovernanceRepository` binding to PostgreSQL migration 0014;
2. auth/request middleware emitting NODE-16 auth/session/membership/token events;
3. NODE-25 Tool Gateway write/destructive/privileged audit emission;
4. Artifact/Asset/Brand/Billing/Approval producers wired to the canonical sink;
5. real object storage GC and search/vector deletion adapters;
6. background retention/deletion/export worker scheduling;
7. KMS/object-store retention and optional external WORM policy where required;
8. jurisdiction-specific retention/deletion policy approval;
9. hosted pinned validation green.

Until those are connected, NODE-65 remains **IMPLEMENTED / VALIDATING / NOT COMPLETE**.
