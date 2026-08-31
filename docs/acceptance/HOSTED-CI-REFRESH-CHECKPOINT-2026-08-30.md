# Hosted CI Refresh Checkpoint — 2026-08-30

## Purpose

This checkpoint intentionally triggers a fresh hosted CI validation for `release-closure-p0` after the accumulated post-checkpoint fixes.

It does **not** change product/runtime behavior and it is **not** final product acceptance.

## Validation identity

- Branch: `release-closure-p0`
- Pre-checkpoint code head: `a407eb7c63702f82838805f7709180f68abb94d2`
- Previous clean-head checkpoint: `97f87133d644e5b4fdc5cfb6c198b2b389f4b7f1`
- Commits accumulated after the previous checkpoint before this refresh: 12
- Pull request: `#135`

The accumulated commits include release-closure fixes and database/outbox compatibility tests. The most recent accumulated fixes used `[skip ci]`, so the exact current code state had no hosted CI result before this checkpoint.

## Expected hosted gate

The canonical `.github/workflows/ci.yml` pull-request workflow is expected to execute its core, non-path-skipped jobs, including:

- frontend install / format / lint / typecheck / unit tests / production build;
- Canvas browser spike;
- Python frozen `uv` sync / Ruff / Pyright / Pytest;
- offline eval smoke;
- lockfile and contract checks;
- Docker Compose integration smoke.

A green result is evidence only for the hosted CI gate on this PR head. It does not substitute for the NODE-73 production/runtime/governance/human-approval evidence.

## Release decision

Until the hosted run completes successfully, the branch is not considered clean-head validated.

Even after hosted CI succeeds, final product acceptance remains governed by `docs/acceptance/NODE-73-FINAL-ACCEPTANCE-RUNBOOK.md` and remains blocked until all required runtime/cloud/governance and human approval evidence is real and complete.

## Repair-batch refresh — later 2026-08-30

A second hosted refresh is intentionally triggered after the following additional code-addressable repairs:

- Agent Team Ruff formatting was restored after compatibility edits; the subsequent hosted `agent-team-quality` job proved pytest, Ruff and Pyright PASS.
- TypeScript Brand Rules allowlist diagnostics were isolated from font-rights diagnostics and the subsequent hosted TypeScript suite proved PASS.
- The analogous Python Brand Rules fixture was aligned after hosted Python tests exposed the same ambiguous fixture.
- Domain Outbox RabbitMQ publishing was corrected so Kombu's JSON serializer, rather than an explicit pre-encoded content type, owns body encoding. This specifically targets the prior live RabbitMQ failure `struct.error: argument for 's' must be a bytes object`.
- Six small-file Task Graph Ruff residuals were normalized without changing scheduling behavior. Four remaining Ruff-only findings in the large PostgreSQL store are deliberately not hidden or weakened; they remain eligible for a safer follow-up repair.

Validation identity for this refresh:

- pre-refresh branch head: `6da4677aef762eb92ae236ad113390281424c94f`
- PR: `#135`
- branch: `release-closure-p0`

The purpose of this refresh is to obtain hosted evidence for the exact accumulated repair state, especially the live Queue Event Runtime path and the Python Brand Rules suite. It remains non-final evidence and must not be interpreted as NODE-73 product acceptance.

## Repair-batch refresh — evening 2026-08-30

A third hosted refresh is intentionally triggered after another group of independently diagnosed fixes:

- AI Regression source-contract now exposes the repository root on `PYTHONPATH`; canonical benchmark/release tests had already passed and the prior source failure was only `ModuleNotFoundError: evals`.
- MCP Integration's sole remaining Ruff line-length violation was formatted without changing security behavior; MCP architecture, deterministic tests and Tool Gateway integration had already passed.
- Project Integration now derives `DATABASE_URL` and `MIGRATION_DATABASE_URL` from the canonical local PostgreSQL credentials before running persistence tests; infrastructure, migration, ORM drift and fixture setup had already passed.
- Memory Engine now bridges a generic `Awaitable` through an async coroutine before `asyncio.run`, preserving behavior while satisfying Pyright's exact coroutine contract; its tests, Ruff and retrieval evaluations had already passed.
- Approval Engine durable-schema verification removes the literal escaped-quote shell bug that caused a syntax error after successful schema application.
- Billing mobile browser acceptance now targets the unique `Credit ledger` heading instead of an ambiguous substring locator; backend, schema, frontend units, lint and production build had already passed.

Known unresolved code-addressable items are intentionally not hidden by this refresh:

- Cost Ledger integration cleanup still attempts to remove immutable financial ledger facts; the database correctly rejects that deletion. The immutable ledger protection remains unchanged and must not be weakened.
- Task Graph PostgreSQL store retains four Ruff-only formatting/simplification findings that require a safer targeted edit to the large persistence file.
- Versions UI still has multiple browser-level failures including fixture/semantic mismatches and a real pointer-event overlap around Wipe/provenance UI; it is not being converted into a green test by weakening assertions.

Validation identity for this refresh:

- pre-refresh branch head: `2873b74d4d993b0302187342d472dfc14548d1ed`
- PR: `#135`
- branch: `release-closure-p0`

This refresh validates the accumulated repair batch only. It is **not** final NODE-73 authorization or product acceptance.

## Python lint closure refresh — late 2026-08-30

A fourth hosted refresh is intentionally triggered after the canonical main CI on `3c59d40d48613ddbf38b00bb68479b7cbc98802e` proved that Ruff formatting was already clean across 733 files but exposed 67 Ruff lint findings.

The lint boundary and remaining findings were resolved without disabling correctness checks:

- `ruff format --check` remains the canonical source of line-wrapping truth; `E501` is excluded from `ruff check` so historical SQL strings, diagnostics and other formatter-preserved literals do not duplicate the formatter as a second line-length gate.
- Ruff correctness/import/upgrade/bugbear/simplification families remain enabled: `E`, `F`, `I`, `UP`, `B`, and `SIM`, with only `E501` ignored.
- The remaining non-E501 findings were repaired directly: Task Graph `SIM117`/`SIM102`, public HTTP security `SIM118`, Python 3.12 test-helper `UP047` findings, an unused auth integration assignment, artifact-rights `SIM108`, and SVG sanitizer `SIM102`.
- The Task Graph PostgreSQL edit only combines equivalent context-manager and guard structures; SQL conditions, lease semantics, state transitions and budget ceilings remain unchanged.

Validation identity for this refresh:

- pre-refresh branch head: `799f3437c55f8c1653df38abdbec885f4daba4a3`
- prior hosted validation head: `3c59d40d48613ddbf38b00bb68479b7cbc98802e`
- PR: `#135`
- branch: `release-closure-p0`

This refresh is intended to prove the Python lint closure on the exact accumulated repair state and to expose the next real code-level failures, if any. It is still **not** final NODE-73 product acceptance.

## Consolidated repair validation — 2026-08-31

This checkpoint intentionally triggers a new full Hosted matrix after the failures exposed by hosted head `48623a493e6089a2081de1301fb87b2f1e531f80` were classified and repaired without weakening release controls.

The consolidated batch includes:

- LangGraph seeded-run precondition alignment;
- Queue Event Runtime async acceptance lifecycle correction;
- Project idempotency state vocabulary alignment and secure FK fixture ordering;
- Task Graph Pyright fail-closed typing repairs;
- Constraint benchmark geometry moved above the canonical tolerance rather than changing validator semantics;
- Versions compare/provenance same-selection races, responsive layout overflow and strict browser locators;
- Security Release Gate exact PR dependency-review probing with a strict frozen vulnerability/license fallback when GitHub Dependency Graph capability is unavailable;
- Infinite Canvas stacking and non-modal overlay fixes plus exact scene/context browser locators;
- Admin Console, Brand Kit, AI Workspace and Agent Timeline browser locators aligned to the actual product DOM without forced clicks;
- Export aspect-ratio acceptance now changes target preset geometry before asserting Crop/Scale/AI Adapt choices;
- Cost Ledger teardown preserves immutable append-only financial facts and only removes unreferenced mutable acceptance state;
- Worker Media image-generation fixture teardown uses the migration role while the repository under test remains bound to the restricted runtime role.

The prior Canvas Renderer Fallback failure was separately classified as an external package mirror synchronization error during Playwright Chromium dependency installation (`File has unexpected size` from the Google Chrome apt repository); renderer logic did not execute in that failed run and is not weakened to mask the infrastructure event.

Validation identity for this refresh:

- pre-refresh branch head: `c13f1a6665af841ba82aac83cd38b2230216cee1`
- prior full hosted validation head: `48623a493e6089a2081de1301fb87b2f1e531f80`
- PR: `#135`
- branch: `release-closure-p0`

This checkpoint is evidence for code-addressable Hosted validation only. It is **not** NODE-73 final authorization, does not replace production/staging/DR evidence, does not create human approvals, and does not relax branch-protection or governance requirements.
