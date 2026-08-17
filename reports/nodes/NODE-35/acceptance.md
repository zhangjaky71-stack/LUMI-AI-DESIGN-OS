# NODE-35 Acceptance — Memory Engine V1

## Status

`IMPLEMENTED -> VALIDATING`

Hosted GitHub Actions remains unverified until a real GitHub runner executes the NODE-35
workflow. A failure with `runner_id=0`, empty `runner_name`, and `steps=[]` must be
classified as `BLOCKED_EXTERNAL`, not as a code failure.

## Delivered

- immutable, content-addressed Memory revisions;
- project / brand / user / organization scopes;
- tenant and scope authorization;
- Agent + invocation permission intersection helper;
- optimistic concurrency with expected parent refs;
- organization-scoped idempotency;
- tombstone-based forget semantics;
- expiry and typed recall filtering;
- deterministic retrieval ranking;
- provenance and source references;
- private-reasoning metadata rejection;
- NODE-34 Context Retrieval adapter with zero instruction authority;
- in-memory and Git-workspace persistence adapters;
- Git-workspace restart reconstruction and chain-corruption checks.

## Local verification

The local execution environment is not a complete repository checkout. NODE-29
`deep_runtime` compatibility stubs from the existing NODE-34 harness are used only to
allow the actual NODE-34 Context Engine package to import. This is isolated contract
validation, not a claim of full hosted repository integration.

Current local results:

- NODE-35 pytest: 15/15 PASS;
- Python compileall: PASS;
- NODE-35 static contract validator: PASS;
- gap-ledger JSON parse: PASS;
- source/test 100-character audit: PASS (0 violations);
- local Ruff: not claimed unless Ruff is actually available and executed.

## Security assertions

- Memory retrieval cannot create SYSTEM, AGENT, or USER instruction authority.
- MEMORY candidates always declare a required memory scope.
- Writes require explicit write scope and reads require explicit read scope.
- Project/brand data never crosses project boundaries.
- Organization/user data never crosses organization boundaries.
- Forget is append-only and cannot rewrite prior provenance.
- Metadata cannot persist private chain-of-thought/scratchpad fields.

## Hosted CI truthfulness

A Hosted Actions green result may be claimed only after checkout/tests actually run. The
known GitHub account runner-allocation problem on preceding nodes is an external blocker
when jobs contain no steps and have `runner_id=0`.
