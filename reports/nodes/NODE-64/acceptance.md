# NODE-64 — Admin Console Acceptance

Status: **IMPLEMENTED / VALIDATING / NOT COMPLETE**

## Implementation evidence

Implementation commit: `4540734e90659386f9bd40a793db6fdfe9020471`

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
- NODE-63 BillingError code/status preserved through Admin API;
- structured AdminAuditSink; deterministic sink never silently no-ops;
- no arbitrary SQL, process-kill or direct payment-state mutation API;
- deterministic browser fixture gated by non-production `LUMI_ADMIN_E2E=1`;
- no package.json / pnpm-lock / uv.lock change required.

## Validation staged

- Project Core platform-admin RBAC / PII / run retry-cancel / provider / queue / billing / View-as / audit tests;
- FastAPI Admin router tests;
- App Shell platform-admin principal contract test;
- frontend admin contract/gateway units;
- Admin Console browser E2E/mobile;
- production fixture-leak scan;
- prior NODE-63 through NODE-54 regressions.

These suites are **STAGED**, not observed PASS, because the hosted runner did not start.

## Hosted pinned validation evidence

Workflow: **Admin Console**  
Run: `31873686332`  
Run number: `1`  
Head SHA: `4540734e90659386f9bd40a793db6fdfe9020471`

| Job | Job/check ID | Result | Execution evidence |
| --- | ---: | --- | --- |
| `admin-contract` | `94986053274` | failure | `runner_id=0`, `runner_name=""`, `steps=[]` — runner never started |
| `admin-backend` | `94986058630` | skipped | dependency did not run |
| `admin-build` | `94986058647` | skipped | dependency did not run |
| `admin-browser-e2e` | `94986058794` | skipped | dependencies did not run |
| `admin-quality` | `94986058881` | skipped | dependency did not run |

GitHub check annotation:

> The job was not started because recent account payments have failed or your spending limit needs to be increased. Please check the 'Billing & plans' section in your settings

Classification: **BLOCKED BEFORE RUNNER**.

This is an account/platform validation blocker. It is **not** a NODE-64 code/test failure and it is **not** a PASS. No checkout, dependency install, static validator, Pyright, pytest, Ruff, TypeScript typecheck, Vitest, lint, production build or Playwright step executed in this hosted run.

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
