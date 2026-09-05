# Runbook — Bad Deploy Rollback

Owner: Release / Platform  
Principle: **roll application code back before rolling data back. Database restore is a last resort with explicit RPO cost.**

## Trigger

Use for elevated errors, broken workflows, incompatible UI/API behavior, failed worker/agent release, or a migration-related production regression immediately after deployment.

## Immediate actions

1. Stop the rollout and record the exact failing image digest, commit, migration head, feature flags and start time.
2. Reduce/fence mutating traffic if continued writes could corrupt state or trigger paid side effects.
3. Preserve logs/traces/audit evidence.
4. Compare the last known-good immutable image digest with current database schema compatibility.

## Preferred rollback order

1. Disable/revert the risky feature flag when it fully contains the failure.
2. Roll back stateless Web/API/Worker/Agent services to the last known-good **immutable image digest**.
3. Keep the database at the newer schema when the migration followed expand/contract compatibility and the old application version is documented to work with it.
4. Reconcile in-flight tasks/provider operations using `agent-run-reconciliation.md` before reopening full traffic.

## Database migration rule

- Production migrations must prefer expand -> dual-read/write/compatibility -> backfill -> contract.
- Do not run Alembic downgrade automatically during an incident.
- Destructive/contract migrations require an explicit rollback plan and compatibility window before deployment.
- If the database itself is corrupt or an irreversible data migration caused loss, invoke `db-restore.md` and accept the measured RPO/data-loss window explicitly.

## Validation

Before restoring normal traffic:

- `/health/ready` and critical API smoke pass.
- Auth/tenant isolation smoke passes.
- Existing projects/assets/artifacts are readable.
- A non-paid Agent command can be accepted/resumed.
- Queue/DLQ is stable.
- No new `ambiguous` idempotency operations are accumulating.
- Cost Ledger/provider signals show no duplicate paid side effects.
- Observability error/latency signals recover.

## STOP conditions

- Last known-good image is not schema compatible.
- Rollback would silently drop/ignore data written by the new release.
- Provider/paid side effects are ambiguous and the old version would retry them differently.
- Cross-tenant/security invariant is violated.

## Exit criteria

- Stable immutable release digest deployed.
- Schema compatibility documented.
- In-flight recovery workload classified.
- Error/latency and critical workflow smoke recovered.
- Incident timeline includes release start, rollback start, service recovery and any user/data impact.
