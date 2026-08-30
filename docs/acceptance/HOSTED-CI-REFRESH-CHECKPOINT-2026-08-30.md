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
