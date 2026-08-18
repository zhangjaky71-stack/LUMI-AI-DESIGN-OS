# NODE-62 Acceptance Evidence — Approval Engine

Status: **CORE IMPLEMENTED / VALIDATING / NOT COMPLETE**

## Implemented and reviewable

- Formal durable Approval domain with separate request, immutable decision, audit, and retryable effect records.
- Linear Alembic migration `20260818_0021 -> 20260818_0022`.
- Artifact approval binds an exact `artifact_version_id`, `artifact:vN` ref and `content_hash` snapshot.
- v4 appearing does not make a v3 Approval drift to head/latest; decision rechecks v3 itself.
- Request, decision and effect operations are UUID-idempotent and tenant scoped.
- Formal decision derives actor + permissions from authenticated request context and requires `artifact.approve`.
- Reject / Changes Requested require feedback and preserve structured Canvas node refs.
- Expired and stale subjects transition durably to EXPIRED/SUPERSEDED before stale is reported.
- Approval Outbox payload is ID/decision oriented and does not copy human feedback text into notifications.
- Approval audit is separate and browser audit read requires `admin.audit.read`.
- Durable effect processor and Artifact/Agent bridge adapters exist; Graph resume payload includes formal `approval_id + decision`.
- Public Approval DTOs omit Graph interrupt/resume IDs, raw effect payload, raw last_error, provider/storage internals.
- Workspace Formal Approval Panel is exact-version scoped and role projected.
- Legacy Workspace `Approve & continue -> resumeAgentRun` bypass is removed.
- Legacy Artifact approve request cannot submit `approved_by_id` and fails closed for browser direct approval.

## Explicitly not accepted as complete

- Production `approval_service_factory` composition.
- Recipe/Graph node creation of durable Approval and interrupt containing `approval_id`.
- Production approval effect worker, RUNNING crash lease/reclaim and DLQ/escalation.
- Production composition of ArtifactEngine and AgentRun effect adapters.
- Graph restart/stale interrupt E2E.
- Automatic `CHANGES_REQUESTED -> Edit/Repair task -> re-review` loop.
- Multi-approver policy execution beyond ANY_ONE v1.
- Non-Artifact subject resolvers and product surfaces.
- Notification consumer/reminder/escalation UX.
- Browser + PostgreSQL + Agent runtime E2E.
- Hosted GitHub Actions executing real NODE-62 steps green.

## Acceptance rule

NODE-62 stays **NOT COMPLETE** while any P0 gap in `gap-ledger.json` remains open or hosted CI has not executed the required migration/test/typecheck/lint/build steps successfully.
