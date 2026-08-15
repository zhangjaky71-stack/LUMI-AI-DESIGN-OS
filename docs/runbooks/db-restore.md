# Runbook — PostgreSQL Restore / PITR

Owner: Platform / Database  
Severity: SEV-1 when production data is unavailable or corrupt  
Rule: **restore into an isolated destination first; never restore over the only production copy.**

## Trigger

Use this runbook for primary database loss/corruption, operator data-loss incident, region failure, or a required point-in-time rollback. A bad application deploy with a healthy database should use `bad-deploy-rollback.md` first.

## Preconditions

- Incident commander and database owner named.
- Writes stopped or fenced if the source can still accept traffic.
- Restore target/time or named recovery point chosen from evidence, not guesswork.
- Matching application image/schema compatibility identified.
- Backup/WAL credentials come from the secret manager; do not paste them into tickets/chat/logs.
- Destination network, account/project and storage are isolated from the current primary.

## Local drill

The NODE-68 drill proves base backup + WAL archive + named PITR semantics without touching production:

```bash
cp -n infra/compose/env.local.example infra/compose/.env
bash scripts/recovery-postgres-drill
```

Expected result: the base-backup row and restore-point-before row exist in the isolated database; the row committed after the restore point does not. The script prints local WAL archive latency and restore RTO. These numbers are **not** production RPO/RTO evidence.

## Production procedure

1. Declare the incident and freeze mutating traffic. Keep read-only access only when it cannot worsen corruption.
2. Preserve the failed primary and audit/telemetry evidence. Do not delete volumes, WAL, snapshots or object versions.
3. Select the latest known-good base backup and WAL range that satisfies the target recovery point.
4. Restore into a new isolated database/cluster. For a managed PostgreSQL service, use its PITR mechanism; for self-managed PostgreSQL, use a verified base backup plus `restore_command`/recovery target semantics equivalent to the NODE-68 drill.
5. Start the restored database with no public application traffic.
6. Use the matching schema/application release and run the read-only verifier:

```bash
export LUMI_RECOVERY_DATABASE_URL='postgresql://...isolated-restore...'
bash scripts/recovery-db-verify
bash scripts/recovery-workload-report
```

7. Verify manually in addition to automated invariants:
   - Alembic/schema version is the intended version.
   - Critical organizations/projects/artifacts can be read.
   - `asset_files` / `artifact_files` object references and SHA-256 samples resolve against object storage.
   - Cost Ledger totals/reversals reconcile with provider/billing evidence.
   - No cross-tenant parent/child mismatch exists.
   - `ambiguous` idempotency operations are inventoried for manual/provider reconciliation.
   - Non-terminal Agent/Task state is classified with `agent-run-reconciliation.md`.
8. Measure actual recovery point and calculate data-loss interval (RPO evidence). Measure from incident recovery decision/start to verified service-ready state (RTO evidence).
9. Before cutover, fence the old primary from writes. Never run old and restored primaries as independent writers.
10. Point application secrets/service discovery to the restored database, initially at reduced traffic/capacity.
11. Run API readiness, authorization/tenant smoke, object-reference sample, Cost Ledger and critical workflow checks.
12. Resume consumers/workers only after queue and Agent reconciliation plans are approved.
13. Restore normal traffic gradually and keep the old primary preserved until the incident owner closes the rollback window.

## STOP conditions

Do not cut over if any of the following is true:

- `recovery-db-verify` reports a hard invariant violation.
- Required WAL is missing or backup manifest verification fails.
- Target recovery point cannot be established.
- Object references materially disagree with restored DB state.
- Cost Ledger/provider reconciliation is unresolved for paid side effects.
- Cross-tenant data mismatch appears.
- Application/schema compatibility is uncertain.

## Exit criteria

- Restored DB invariants PASS.
- Object/checksum samples PASS.
- Recovery workload is classified; ambiguous/external items are not blindly retried.
- Measured RPO/RTO recorded in the NODE-68 evidence ledger.
- Post-incident backup/PITR gap and remediation owner recorded.
