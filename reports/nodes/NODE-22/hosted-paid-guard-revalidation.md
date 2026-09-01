# NODE-22 Hosted Paid-Guard Revalidation

This evidence record intentionally exists to trigger and bind a normal pull-request execution of the canonical Model Gateway workflow after the fail-closed PostgreSQL idempotency fixes were committed by the verified one-shot remediation.

## Canonical fixes under revalidation

- `result_json` is decoded through a fail-closed JSON-object boundary so asyncpg JSONB text results cannot be misinterpreted as mapping iterables.
- retry-safe failure persistence binds the shared status parameter explicitly as `varchar(32)` so asyncpg does not infer conflicting `text` / `character varying` parameter types.
- malformed persisted JSON is rejected rather than silently accepted.

## Formal normal-workflow result

Normal pull-request workflow **Model Gateway** run `32683538121` completed successfully on the release-closure branch after the fixes landed.

All three canonical jobs passed:

1. `source-contract`
   - source compilation
   - architecture / secret boundary validation
   - Deep Agents private Model Gateway binding
   - cross-layer private deployment contract
2. `model-gateway`
   - frozen workspace installation
   - architecture and private deployment validators
   - Ruff
   - Pyright
   - Model Gateway unit tests
   - hosted media output boundary tests
   - Deep Agents HTTP model-boundary tests
   - paid-guard unit tests
   - mock-provider full integration
   - proof that no live provider credential is required
3. `hosted-paid-guard-postgres`
   - local infrastructure startup
   - database upgrade and ORM drift validation
   - durable paid invocation PostgreSQL acceptance
   - migration downgrade / re-upgrade smoke
   - cleanup

This is code-addressable release evidence only. It does not replace NODE-71 sealed Staging evidence, NODE-72 exact-digest promotion evidence, live-provider benchmarks, production deployment evidence, or NODE-73 dispatch-only Final Acceptance.
