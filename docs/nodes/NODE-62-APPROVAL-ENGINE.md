# NODE-62 — Approval & Review Workflow

> Phase: 8 SaaS & Collaboration  
> Status: **IMPLEMENTED / VALIDATING / NOT COMPLETE**  
> Priority: P0/P1 CORE WORKFLOW  
> Depends on: NODE-28 Recipe Engine, NODE-42 Artifact History, NODE-57 Agent Timeline, NODE-61 Collaboration  
> Produces: formal Approval Domain, exact-version decision lock, LangGraph interrupt/resume bridge, Request Changes handoff, audit and Approval Center UX

---

## 1. Goal

NODE-62 turns Human-in-the-loop from an Agent-runtime interrupt into a durable product workflow.

Users may approve:

```text
CREATIVE_DIRECTION
ARTIFACT_VERSION
BRAND_RULE_SET
BUDGET_INCREASE
EXTERNAL_PUBLISH
DESTRUCTIVE_ACTION
CUSTOM_REVIEW
```

The critical invariant is:

```text
approval decision != approval of "whatever is latest"
```

Every Approval is bound to an immutable `{subject_type, subject_id, subject_version}`. The words `latest`, `head`, and `current` are rejected as subject versions.

## 2. Canonical flow

```text
Recipe / Agent task
  -> create durable Approval(PENDING)
  -> persist before interrupt
  -> LangGraph interrupt({approval_id, exact subject identity, safe summary})
  -> Approval Center / Workspace read projection
  -> authorized user decision API + Idempotency-Key
  -> transaction validates permission/version/status/expiry/run state
  -> append immutable decision + audit
  -> APPROVED / REJECTED / CHANGES_REQUESTED
  -> LangGraph Command(resume={approval_id, decision, exact subject_version, feedback?})
```

The Approval store is canonical. Browser state, Agent event streams, LangGraph interrupt payloads and timeline cards are read projections/transports only.

## 3. Approval Record

Canonical record:

```text
approval_id
organization_id
project_id
agent_run_id?
task_id?
approval_type
subject_type
subject_id
subject_version
status
requested_by
policy
payload_summary
expires_at?
created_at
resolved_at?
resolved_by?
decisions[]
feedback?
superseded_by?
```

Statuses:

```text
PENDING
APPROVED
REJECTED
CHANGES_REQUESTED
EXPIRED
CANCELLED
SUPERSEDED
```

## 4. Exact-version protection

Example:

```text
Approval A -> Artifact artifact-1 / artifact-v3
new ArtifactVersion artifact-v4 appears
```

Approval A never becomes approval for v4.

If a new Approval is requested for the same subject identity at v4 while the v3 Approval is still PENDING, the v3 Approval becomes `SUPERSEDED` and retains `subject_version=artifact-v3` plus `superseded_by=<new approval id>`.

A decision checks that the exact subject still exists. If it does not, decision fails closed with `APPROVAL_STALE`.

## 5. Authorization

NODE-62 does not create another RBAC system.

Trusted NODE-16 actor context provides current roles and permissions. Decision-time policy checks:

```text
required_permission
required_roles[]
policy mode / quorum / role sequence
```

Typical mapping:

```text
ARTIFACT_VERSION -> artifact.approve
BRAND_RULE_SET -> brand.manage
BUDGET_INCREASE -> billing.manage
EXTERNAL_PUBLISH -> project.write + configured policy
DESTRUCTIVE_ACTION -> project.write + configured policy
```

The UI receives only a server-computed `can_decide` affordance. The server remains authoritative and rechecks permission on every decision.

## 6. Idempotency

Every decision API requires an `Idempotency-Key`.

Rules:

1. replay same key against same Approval -> return stored result;
2. reuse same key for another Approval -> reject;
3. independent second decision after P0 terminal resolution -> `APPROVAL_STALE`;
4. Graph resume is driven only from the committed Approval result.

This protects double-clicks, request retries, mobile reconnects and proxy retries.

## 7. Request Changes

`REQUEST_CHANGES` is not an approval alias.

Structured feedback:

```text
comment
node_refs[]
region_refs[]
requested_changes[]
```

`ApprovalChangesPort` converts this into edit/repair tasks. The Agent graph receives a resume envelope with `decision=REQUEST_CHANGES`, exact subject version and feedback, so the recipe routes back to edit/repair rather than continuing down the approved branch.

## 8. Multi-approver policy

Runtime/schema support:

```text
ANY_ONE
ALL
MIN_N
ROLE_BASED_SEQUENCE
```

P0 defaults to ANY_ONE. Every policy has `policy_version`.

Semantics:

- ANY_ONE: first authorized approve resolves;
- ALL: all configured required roles must be represented;
- MIN_N: N unique authorized actors;
- ROLE_BASED_SEQUENCE: required roles approve in configured order.

Reject and Request Changes resolve immediately in the current workflow contract.

## 9. Expiry

High-risk Approval may carry `expires_at`.

Expiry is fail-closed:

```text
PENDING + expires_at <= now -> EXPIRED
```

No scheduler is required for correctness because every read/decision also checks expiry. A future scheduler may proactively materialize expiry events.

## 10. LangGraph bridge

`apps/agent-runtime/src/lumi_agent_runtime/recipe_engine/approval_bridge.py`

The bridge uses LangGraph's `interrupt` and `Command(resume=...)` but does not import Project Core at runtime. It consumes structural Protocols so the Agent Runtime retains its current deployment dependency boundary.

Persist-before-interrupt is mandatory:

```text
create Approval row
COMMIT
interrupt_for_approval(approval)
```

After process restart, the workflow resumes using the durable `approval_id`; it does not require the old process memory.

## 11. Notifications

Approval-required in-app notification reuses NODE-61 `collaboration_notifications` through `ApprovalNotificationPort` with `APPROVAL_REQUEST` semantics.

NODE-62 intentionally does not add a second notification database.

P1 email is a delivery adapter over the same canonical event and must respect reminder throttling/preferences.

## 12. Audit

Immutable audit events include:

```text
APPROVAL_REQUESTED
APPROVAL_DECISION_RECORDED
APPROVAL_APPROVED
APPROVAL_REJECTED
APPROVAL_CHANGES_REQUESTED
APPROVAL_CHANGE_TASKS_CREATED
APPROVAL_EXPIRED
APPROVAL_CANCELLED
APPROVAL_SUPERSEDED
```

Audit captures actor, exact subject identity/version and safe metadata. Raw prompts, secrets, signed URLs and private reasoning are excluded.

## 13. Persistence

Migration:

```text
db/migrations/0012_approval_engine.sql
```

Durable tables:

```text
approvals
approval_decisions
approval_change_requests
approval_audit_events
```

Decision and change-request FKs are tenant/project composite references. `approval_decisions` has a tenant-scoped unique idempotency key.

Notifications reuse NODE-61 persistence.

## 14. API

Product transport factory:

```text
GET  /projects/{projectId}/approvals
GET  /projects/{projectId}/approvals/{approvalId}
POST /projects/{projectId}/approvals
POST /projects/{projectId}/approvals/{approvalId}:decide
POST /projects/{projectId}/approvals/{approvalId}:cancel
```

Public request creation requires `project.write`. Decision authorization remains the domain policy's `required_permission` / role contract.

API errors expose safe error code/message and opaque request ID only.

## 15. Product UI

Route:

```text
/app/projects/{projectId}/approvals
```

Approval Center provides:

- Waiting / History filters;
- exact subject identity/version;
- PENDING vs terminal state;
- superseded historical Approval visibility;
- policy/quorum/sequence summary;
- expiry and Agent run context;
- Approve exact version;
- Reject;
- Request Changes with feedback;
- safe error/request ID;
- deep link back to Agent Workspace;
- responsive mobile layout.

The Project page links directly to Approvals.

## 16. Existing Workspace integration

NODE-54/57 `WorkspaceApproval` remains a **read projection** for inline Agent cards/timeline. It is not a second durable Approval domain.

Production integration must project NODE-62 Approval records into those cards and route decisions through the NODE-62 decision API.

## 17. Tests staged

Backend:

- approve exact version;
- v3 superseded by v4 without retargeting;
- unauthorized Viewer;
- duplicate decision idempotency;
- Request Changes -> change task;
- expiry;
- missing subject -> stale;
- process/graph restart while waiting;
- MIN_N;
- ROLE_BASED_SEQUENCE.

Agent bridge:

- exact approval ID and subject version in resume payload/Command.

API:

- request/list/decision;
- permission gate;
- structured Request Changes;
- safe request ID projection.

Database:

- four canonical Approval tables;
- JSON policy/feedback structures;
- tenant/project composite FKs;
- floating version rejection.

Browser:

- pending exact version;
- superseded history;
- approve moves to immutable history;
- request changes feedback;
- mobile.

## 18. Production integration gates

The protocol, domain, migration, API factory, LangGraph bridge and product UI are implemented. NODE-62 remains NOT COMPLETE until:

1. durable PostgreSQL Approval repository/decision/change/audit adapters are bound;
2. NODE-16 trusted actor/session resolver is wired into the deployed router;
3. NODE-28 recipe execution calls persist-before-interrupt;
4. deployed LangGraph checkpoint/resume dispatcher executes `Command(resume=...)`;
5. NODE-42/Brand/Budget/External exact-subject resolver is bound;
6. NODE-61 notification adapter is bound;
7. NODE-54/57 inline Approval read projections consume NODE-62 production truth;
8. hosted pinned validation executes green.

These are explicit deployment gates, not represented as completed by deterministic adapters.

## 19. Acceptance

- [x] Approval is a formal Domain object;
- [x] exact version locked;
- [x] stale/unauthorized decisions fail closed;
- [x] duplicate decision idempotency contract;
- [x] Request Changes routes to repair/edit workflow port;
- [x] expiry fail-closed;
- [x] durable audit contract;
- [x] LangGraph restart-safe approval_id bridge;
- [x] multi-approver policy support;
- [x] Approval Center UI;
- [x] database/API/unit/browser validation staged;
- [ ] production adapters connected;
- [ ] hosted pinned gates observed green.

## 20. Definition of Done

```text
Approval domain/API/UI/Graph bridge implemented
+ PostgreSQL adapters connected
+ NODE-16/NODE-28/NODE-42/NODE-61 integrations connected
+ stale/restart/idempotency/Request Changes E2E green
+ hosted pinned gates green
```

Next: **NODE-63 — Billing**.
