# NODE-61 — Collaboration Acceptance

Status: **IMPLEMENTED / VALIDATING / NOT COMPLETE**

## Implementation evidence

- canonical CollaborationEngine added to existing `lumi-project-core` without a new workspace dependency;
- Project collaboration route and responsive product UI added;
- exact ArtifactVersion + DesignVersion review anchors implemented;
- OPEN / RESOLVED / REOPENED threads, replies, edit/delete audit semantics implemented;
- mention permission gate and safe notifications implemented;
- USER vs AGENT actor identity with required `agent_run_id` implemented;
- presence/cursor/selection kept ephemeral;
- tenant/project view gate runs before presence join;
- property-key conflict strategy implemented;
- stale non-conflicting operations rebase;
- same-property local operations survive conflict response;
- reconnect reuses canonical rebase path;
- Hard Constraint validation precedes accepted canonical commit;
- WebSocket canonical mutations explicitly rejected;
- Project bootstrap resolves canonical document context server-side rather than browser guessing;
- collaboration SQL migration contains durable review/audit/notification tables and no presence table;
- deterministic browser fixture gated by non-production `LUMI_COLLABORATION_E2E=1`;
- no package.json, pnpm-lock or uv.lock change is required by the implementation design.

## Tests staged

- Project Core concurrency/rebase/conflict/reconnect/constraint/agent/restart tests;
- FastAPI transport + awareness-only WebSocket tests;
- PostgreSQL migration contract;
- frontend contract/gateway unit tests;
- browser presence/comment/history/thread/concurrency/mobile scenarios;
- production build fixture-leak scan;
- NODE-60 through NODE-54 browser regressions.

These suites are **STAGED** until hosted runners actually execute them.

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
- [x] durable schema excludes realtime presence;
- [x] static/unit/API/DB/browser validation staged;
- [ ] production adapters connected;
- [ ] hosted pinned validation observed green.

Hosted evidence will be appended after the implementation commit triggers GitHub Actions.
