# Approval Engine Runtime V1

## Canonical flow

```text
Recipe / Agent task
  -> persist Approval(PENDING) with exact subject_version
  -> LangGraph interrupt({approval_id, exact subject identity, safe summary})
  -> Approval Center / Workspace read projection
  -> POST decision + Idempotency-Key
  -> transactional validation
       tenant/project
       required_permission / role
       exact subject still exists
       status still PENDING
       expiry not elapsed
       agent run still resumable
       multi-approver policy ordering/quorum
  -> immutable decision + audit
  -> APPROVED / REJECTED / CHANGES_REQUESTED
  -> Command(resume={approval_id, decision, exact subject_version, feedback?})
```

The Approval database is the decision source of truth. LangGraph checkpoints hold only `approval_id` and safe interrupt/resume data; a process restart must recover the approval from durable storage rather than from browser state.

## Exact subject invariant

An Approval binds `{subject_type, subject_id, subject_version}`. `latest`, `head`, and `current` are rejected. A v3 decision can never authorize v4. Requesting approval for the same subject identity at a newer version supersedes an older still-PENDING Approval without changing the old record's v3 subject.

## Decision idempotency

Every decision command requires an idempotency key. Replaying the same key for the same approval returns the stored result. Reusing the key for another approval fails. A second independent decision after a P0 terminal result returns `APPROVAL_STALE`.

## Request Changes

`REQUEST_CHANGES` requires structured feedback and resolves the current approval as `CHANGES_REQUESTED`. `ApprovalChangesPort` converts feedback into repair/edit tasks. The Graph resumes with the decision and exact subject version so the recipe can route back to edit/repair instead of continuing through the approved branch.

## Multi-approver policy

Schema/runtime support:
- `ANY_ONE` — first authorized approve resolves;
- `ALL` — all required roles must be represented;
- `MIN_N` — N unique authorized actors;
- `ROLE_BASED_SEQUENCE` — required roles act in sequence.

Every policy has an immutable `policy_version`. P0 defaults to ANY_ONE; richer policies can be enabled without changing the Approval identity contract.

## Expiry

Expiry is fail-closed. Reading/deciding an elapsed PENDING approval transitions it to `EXPIRED`; it is never implicitly approved. Production scheduling may proactively call the same expiry path, but correctness cannot depend on a scheduler firing exactly on time.

## Notifications

NODE-62 does not create another notification database. `ApprovalNotificationPort` must bind to NODE-61 `collaboration_notifications` with kind `APPROVAL_REQUEST`. P1 email is a delivery adapter over the same canonical approval event and must obey reminder throttling/preferences.

## Audit

`APPROVAL_REQUESTED`, every decision/quorum step, `APPROVAL_APPROVED`, `APPROVAL_REJECTED`, `APPROVAL_CHANGES_REQUESTED`, `APPROVAL_EXPIRED`, `APPROVAL_CANCELLED`, and `APPROVAL_SUPERSEDED` are immutable audit events. Safe metadata excludes full prompts, raw backend payloads, secrets and signed URLs.

## Production integration gates

1. PostgreSQL repository for approvals/decisions/change requests/audit using `0012_approval_engine.sql`.
2. NODE-28 recipe runtime creation point calls persist-before-interrupt.
3. LangGraph checkpoint/resume adapter delivers `Command(resume=...)` after decision.
4. NODE-42 Artifact/Brand/Budget/External subject resolver provides exact subject existence.
5. NODE-16 trusted actor resolver supplies current roles/permissions.
6. NODE-61 in-app notification adapter receives approval-required events.
7. Production UI obtains actor capability projection from the trusted session/API.

Until these adapters are deployed and hosted gates execute green, NODE-62 remains IMPLEMENTED / VALIDATING / NOT COMPLETE.
