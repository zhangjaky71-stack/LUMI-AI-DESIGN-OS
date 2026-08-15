# NODE-62 — Approval Engine Acceptance

Status: **IMPLEMENTED / VALIDATING / NOT COMPLETE**

## Implementation evidence

- formal Approval domain object and lifecycle implemented;
- seven canonical approval types and statuses implemented;
- exact `{subject_type, subject_id, subject_version}` binding; floating latest/head/current rejected;
- new exact-version request supersedes older pending request without retargeting it;
- required permission/role checked at decision time;
- subject existence, PENDING status, expiry and run-resume stale checks fail closed;
- idempotent decision key contract implemented;
- Request Changes structured feedback routes to change-task port;
- ANY_ONE / ALL / MIN_N / ROLE_BASED_SEQUENCE policy contract with policy version implemented;
- LangGraph interrupt/resume bridge uses approval_id and exact subject version without adding an undeclared Agent Runtime → Project Core package dependency;
- audit and notification ports implemented;
- `0012_approval_engine.sql` adds approvals, decisions, structured change requests and immutable audit events;
- decision/change-request relations use tenant+project composite foreign keys;
- approval notifications intentionally reuse NODE-61 notification truth;
- `/app/projects/{projectId}/approvals` Approval Center implemented;
- Approval list API returns trusted actor id + server-computed `can_decide` affordance while the decision endpoint remains authoritative;
- Waiting/History, exact subject, superseded history, policy, expiry, Agent run, approve/reject/request-changes and mobile UX implemented;
- deterministic browser fixture is gated by non-production `LUMI_APPROVAL_E2E=1`;
- no browser localStorage/sessionStorage/IndexedDB approval truth;
- no package.json, pnpm-lock or uv.lock change required.

## Validation staged

- approval domain exact-version/stale/permission/idempotency/request-changes/expiry/restart/multi-approver tests;
- LangGraph Command resume contract test;
- FastAPI request/list/decision/request-changes transport tests;
- PostgreSQL schema and composite tenant FK checks;
- frontend contract/gateway unit tests;
- Approval Center browser E2E and NODE-61 through NODE-54 regressions;
- production build deterministic-fixture leakage scan.

These suites are **STAGED**, not observed PASS, until hosted runners execute them.

## Explicit production integration gates

- [ ] bind durable PostgreSQL Approval repository/decision/audit/change-request adapters with transactional decision CAS semantics;
- [ ] bind NODE-16 actor/session permission resolver in the deployed API;
- [ ] bind NODE-28 persist-before-interrupt recipe integration;
- [ ] bind LangGraph durable checkpoint/resume dispatcher;
- [ ] bind NODE-42 exact subject resolvers;
- [ ] bind NODE-61 in-app notification adapter;
- [ ] project NODE-62 canonical approvals into NODE-54/57 inline Approval cards/timeline;
- [ ] hosted pinned gates execute green.

The in-memory repository, subject/run adapters and deterministic browser gateway are test/dev evidence only. They are not represented as production persistence or transactional concurrency proof.

## Definition of Done

- [x] Approval is a formal domain object;
- [x] exact subject version locked;
- [x] stale/unauthorized fail closed;
- [x] duplicate decision idempotency contract;
- [x] Request Changes re-enters edit/repair workflow via port;
- [x] immutable audit contract;
- [x] Approval Center product UI;
- [x] restart-safe approval_id Graph bridge contract;
- [x] multi-approver schema/runtime policy support;
- [x] unit/API/DB/browser validation staged;
- [ ] production adapters connected;
- [ ] hosted pinned validation observed green.

Hosted evidence will be appended after the implementation commit triggers GitHub Actions.
