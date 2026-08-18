# NODE-51 Acceptance Record

Status: **IMPLEMENTED / VALIDATING / NOT COMPLETE**

## Submitted implementation evidence

- bounded `AutoRepairEngine`, one candidate per resume;
- minimum reversible repair planner with exact no-repeat signatures;
- NODE-39 pre/postflight gates;
- NODE-27 repair-budget envelope with downstream provider-cost ownership;
- NODE-38 typed DesignOperation backend and fail-closed preview renderer port;
- NODE-47 isolated `target_branch_id` local-edit path;
- NODE-42 repair branch, staged exact final version, exact NODE-50 re-evaluation, APPROVED-before-CAS head promotion;
- early/late stale conflict protection;
- PostgreSQL policy/job/attempt/learning persistence on migration `20260818_0020`;
- canonical violation-code learning signals with explicit training governance;
- service/API/static regression suites and dedicated NODE-51 workflow.

## Hosted CI evidence

Stacked PR: **#118**, base `feat/node-50-visual-critic`, head `feat/node-51-auto-repair`.

First NODE-51 workflow execution on implementation head `70ddaf7186d4fabbe4e7843013e463d0c54fb496`:

- workflow run: **32086749544** — conclusion `failure`;
- `repair-contract` job: **95560770351** — conclusion `failure`;
- `repair-contract` steps: **empty list (`[]`)**;
- `repair-contract` log fetch: **404 / BlobNotFound**;
- `repair-quality` job: **95560786687** — `skipped`;
- `repair-db` job: **95560786929** — `skipped`.

No checkout, dependency install, compile, static validator, pytest, Ruff, Pyright, Alembic, or PostgreSQL assertion step executed. This run therefore provides **no code-execution evidence**. The same commit also showed many pre-existing repository workflows failing simultaneously, consistent with the previously established account-level pre-run infrastructure/billing blocker. NODE-51 must not treat this as a product-code test failure or as a successful validation.

## Completion blockers

See `reports/nodes/NODE-51/gap-ledger.json`. NODE-51 remains **IMPLEMENTED / VALIDATING / NOT COMPLETE** until Hosted CI produces non-empty executed steps and the remaining P0/P1 production-composition/provider/evaluation gaps are closed.
