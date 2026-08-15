# NODE-61 — Collaboration Acceptance

Status: **IMPLEMENTED / VALIDATING / NOT COMPLETE**

## Implementation evidence

- canonical CollaborationEngine added to existing `lumi-project-core` without a new workspace dependency;
- Project collaboration route and responsive product UI added;
- exact ArtifactVersion + DesignVersion review anchors implemented;
- OPEN / RESOLVED / REOPENED threads, replies, edit/delete audit semantics implemented;
- mention permission gate and safe notifications implemented;
- USER vs AGENT actor identity with required `agent_run_id` implemented;
- NODE-16 role vocabulary preserved; no parallel CLIENT RBAC role introduced;
- presence/cursor/selection kept ephemeral;
- tenant/project view gate runs before presence join;
- property-key conflict strategy implemented;
- stale non-conflicting operations rebase;
- same-property local operations survive conflict response;
- reconnect reuses canonical rebase path;
- Hard Constraint validation precedes accepted canonical commit;
- WebSocket canonical mutations explicitly rejected;
- Project bootstrap resolves canonical document context server-side rather than browser guessing;
- `db/migrations/0011_collaboration.sql` follows existing 0009/0010 migrations without a duplicate sequence number;
- comments/notifications reference threads through organization + project + thread composite foreign keys;
- collaboration SQL contains durable review/audit/notification tables and no presence table;
- deterministic browser fixture gated by non-production `LUMI_COLLABORATION_E2E=1`;
- implementation diff has no package.json, pnpm-lock or uv.lock drift.

## Tests staged

- Project Core concurrency/rebase/conflict/reconnect/constraint/agent/restart tests;
- FastAPI transport + awareness-only WebSocket tests;
- PostgreSQL migration contract;
- frontend contract/gateway unit tests;
- browser presence/comment/history/thread/concurrency/mobile scenarios;
- production build fixture-leak scan;
- NODE-60 through NODE-54 browser regressions.

These suites are **STAGED** until hosted runners actually execute them.

## Hosted validation evidence

Implementation SHA: `58e0c1598458a0364b518d9be7c70539961fff86`  
Workflow: `Collaboration` run `31870628186` (#1)

- `collaboration-contract` / job `94978592664`: **failure before runner**;
- job metadata: `runner_id=0`, `runner_name=""`, `steps=[]`;
- `collaboration-backend` / `94978599154`: skipped;
- `collaboration-db` / `94978599095`: skipped;
- `collaboration-quality` / `94978599119`: skipped;
- `collaboration-build` / `94978598863`: skipped;
- `collaboration-browser-e2e` / `94978599385`: skipped.

GitHub annotation:

> The job was not started because recent account payments have failed or your spending limit needs to be increased. Please check the 'Billing & plans' section in your settings

Classification: **BLOCKED BEFORE RUNNER**.

No checkout, dependency installation, static validator, pyright, TypeScript typecheck, pytest, PostgreSQL migration, unit suite, build or browser E2E step executed. Therefore staged suites are neither observed PASS nor observed code/test failure.

## Explicit production integration gates

- [ ] bind trusted NODE-16 session/tenant actor resolver and Project member directory;
- [ ] bind durable PostgreSQL collaboration repository/audit/notification adapters;
- [ ] bind NODE-40 canonical Design Operation / DesignDocumentVersion adapter;
- [ ] bind Redis/managed multi-instance RealtimeHub/PresenceStore;
- [ ] execute hosted pinned validation green.

The deterministic/in-process adapters are test/dev evidence only and are not represented as production persistence or multi-instance realtime.

## Definition of Done

- [x] collaboration protocol and conflict semantics implemented;
- [x] Collaboration product UI implemented;
- [x] exact historical comments implemented;
- [x] Agent actor audit identity implemented;
- [x] canonical NODE-16 role vocabulary preserved;
- [x] durable schema excludes realtime presence and tenant-scopes thread references;
- [x] static/unit/API/DB/browser validation staged;
- [ ] production adapters connected;
- [ ] hosted pinned validation observed green.
