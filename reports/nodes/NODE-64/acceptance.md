# NODE-64 — Admin Console Acceptance

Status: **IMPLEMENTED / VALIDATING / NOT COMPLETE**

## Implementation evidence

- dedicated PlatformAdminActor and seven platform roles, separate from tenant Organization roles;
- canonical admin permission matrix;
- `/app/admin` platform-principal-only navigation and route gate;
- Overview, Users/Organizations, Runs, Providers, Queue, Registry, Billing and Audit product surfaces;
- default masked email/phone with privileged PII reveal path;
- readonly max-15-minute View-as with owner scoping and start/end audit events;
- exact sensitive action summary + impact scope + reason + ticket + `CONFIRM` contract;
- provider disable future expiry capped at 24 hours;
- queue requeue CAS on immutable original payload ref + SHA-256 with no payload editor;
- run retry/cancel service boundary;
- Agent/Skill registry enable/disable service boundary and readonly deploy diff;
- NODE-63 immutable `ADJUSTMENT` credit ledger adapter with non-negative debit guard;
- structured AdminAuditSink; deterministic sink never silently no-ops;
- no arbitrary SQL, process-kill or direct payment-state mutation API;
- deterministic browser fixture gated by non-production `LUMI_ADMIN_E2E=1`;
- no package.json / pnpm-lock / uv.lock change required.

## Validation staged

- Project Core platform-admin RBAC / PII / provider / queue / billing / View-as / audit tests;
- FastAPI Admin router tests;
- frontend admin contract/gateway units;
- Admin Console browser E2E/mobile;
- production fixture-leak scan;
- prior NODE-63 through NODE-54 regressions.

These suites are **STAGED**, not observed PASS, until hosted runners execute them.

## Explicit production integration gates

- [ ] production NODE-16 platform-admin principal and step-up resolver;
- [ ] production Support Directory adapter;
- [ ] production Run/Task control adapter;
- [ ] production Provider Health/Router control adapter;
- [ ] production Queue/DLQ adapter enforcing immutable payload identity;
- [ ] production Agent/Skill Registry control adapters;
- [ ] NODE-27 provider cost runtime projection;
- [ ] NODE-63 durable BillingRepository transaction adapter;
- [ ] NODE-65 durable append-only Audit & Governance sink;
- [ ] stronger verification/dual-control for production-wide actions;
- [ ] hosted pinned gates execute green.

The deterministic adapters and browser fixture are engineering evidence only. They are not represented as deployed production support access, durable audit, live provider control, live queue control or production billing authority.

## Definition of Done

- [x] Admin Console domain/API/product surface implemented;
- [x] privileged workflows fail closed;
- [x] PII/View-as guardrails implemented;
- [x] Billing adjustment uses NODE-63 ledger semantics;
- [x] audit integration contract implemented;
- [x] tests and CI gates staged;
- [ ] production adapters connected;
- [ ] NODE-65 audit persistence connected;
- [ ] hosted pinned validation observed green.

Hosted evidence will be appended after the implementation commit triggers GitHub Actions.
