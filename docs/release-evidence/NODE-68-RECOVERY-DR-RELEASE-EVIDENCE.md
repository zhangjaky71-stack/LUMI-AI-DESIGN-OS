# NODE-68 — Backup, Recovery & Disaster Readiness — Release Evidence

> Evidence date: 2026-08-15  
> Branch: `node-68-recovery-dr-release`  
> Status: **SOURCE IMPLEMENTED / RELEASE BLOCKED**  
> Release class: P0 / STOP SHIP until runtime drills and production controls are proven

## 1. Decision

NODE-68 has an implementation-complete source baseline for recovery planning, PostgreSQL PITR drills, object-version recovery drills, restored-database verification, recovery workload inventory, and operator runbooks.

This document does **not** claim release readiness. No production or production-like recovery target has been restored and measured from this execution environment. Local/CI drill code being present is not equivalent to a passed restore drill.

## 2. Implemented source controls

| Control | Source state | Runtime evidence |
|---|---|---|
| Fail-closed recovery planner | IMPLEMENTED | NOT EXECUTED here |
| Ambiguous/provider side effects never blind-retry | IMPLEMENTED | NOT EXECUTED here |
| PostgreSQL continuous WAL archive overlay | IMPLEMENTED | NOT EXECUTED here |
| Verified `pg_basebackup` + `pg_verifybackup` | IMPLEMENTED | NOT EXECUTED here |
| Isolated named-restore-point PITR drill | IMPLEMENTED | NOT EXECUTED here |
| MinIO bucket versioning baseline | IMPLEMENTED | NOT EXECUTED here |
| Object delete/rewind/recover drill | IMPLEMENTED | NOT EXECUTED here |
| Read-only restored DB invariant verification | IMPLEMENTED | NOT EXECUTED here |
| Recovery workload inventory | IMPLEMENTED | NOT EXECUTED here |
| RabbitMQ rebuild procedure from DB/outbox truth | DOCUMENTED | DRILL PENDING |
| AgentRun checkpoint/provider reconciliation procedure | DOCUMENTED | DRILL PENDING |
| Bad deploy rollback procedure | DOCUMENTED | DRILL PENDING |
| Provider outage procedure | DOCUMENTED | DRILL PENDING |
| Security incident recovery procedure | DOCUMENTED | DRILL PENDING |
| Recovery Contract CI | IMPLEMENTED | RUNNER EXECUTION PENDING |

## 3. Safety invariants frozen in source

1. PostgreSQL is the business source of truth; RabbitMQ queue contents are not.
2. Persisted outbox replay preserves the original event identity so inbox deduplication remains effective.
3. `ambiguous` operations are never automatically retried.
4. An operation with a provider-native request ID must reconcile provider state before any retry.
5. External tasks are reconciled before requeue.
6. Agent runs resume only from durable checkpoint/control state; missing or incompatible state is quarantined/manual.
7. Restored-database verification is read-only and requires explicit isolated-target acknowledgement.
8. The local PITR restore writes only to a dedicated restore volume; destructive restore initialization requires `LUMI_RECOVERY_ISOLATED=1`.
9. Object recovery drill is restricted to `_node68-drill/<id>/` and cleanup is restricted to that prefix.
10. Local drill timing must never be reported as production RPO/RTO.

## 4. Local drill contract

Available operator entry points:

```bash
make recovery-postgres-drill
make recovery-object-drill
make recovery-drill
make recovery-db-verify
make recovery-workload
make recovery-down
```

`make recovery-drill` is designed to prove the mechanics of:

- verified base backup;
- continuous WAL archiving;
- named restore point;
- isolated PITR restore;
- pre-target data survives while post-target data does not;
- versioned-object delete and recovery.

The script prints local WAL archive latency and local restore duration, explicitly labelled as non-production evidence.

## 5. Recovery Contract CI

`.github/workflows/recovery-contract.yml` contains two layers:

### PR source contract

- dependency-free recovery planner contract;
- required recovery file/runbook presence;
- shell syntax validation;
- recovery Compose render validation.

This layer intentionally does not bypass or rewrite the repository Python lockfile.

### Manual destructive drill

`workflow_dispatch` only:

- PostgreSQL PITR drill;
- object version/delete/recover drill;
- drill log artifact upload;
- unconditional local infrastructure cleanup.

A successful manual CI drill is useful engineering evidence, but still does not replace a production-like restore exercise.

## 6. Required release evidence still missing

The following remain **STOP SHIP**:

- [ ] Recovery Contract jobs actually execute successfully on a GitHub runner.
- [ ] Real isolated PostgreSQL restore from the selected staging/production backup system.
- [ ] Measured PostgreSQL RPO <= 5 minutes on the chosen production backup/WAL architecture.
- [ ] Measured PostgreSQL RTO <= 60 minutes for the agreed production data size/runbook.
- [ ] Production backup encryption, retention, deletion protection, least privilege and access audit verified.
- [ ] Production-capable object storage versioning/recovery verified against real bucket controls.
- [ ] Object backup/replication RPO policy frozen for production.
- [ ] Redis loss/rebuild drill completed with conservative rate-limit behavior verified.
- [ ] RabbitMQ loss/rebuild drill completed from PostgreSQL/outbox truth.
- [ ] AgentRun restart/resume/reconcile drill completed, including WAITING_USER and external/provider uncertainty.
- [ ] Bad deploy rollback drill completed against schema-compatible and schema-incompatible cases.
- [ ] Provider outage exercise completed without duplicate paid effects.
- [ ] Region-level tabletop/restore capability recorded according to NODE-72 deployment budget.
- [ ] Root `uv.lock` freshness blocker inherited from NODE-66 is resolved and the canonical security/supply-chain gates pass.

## 7. Known external validation blocker

Recent NODE-66/NODE-67 GitHub Actions runs did not receive runners because of the repository/account Billing / spending-limit condition. Those runs showed no executed steps, so they are platform-blocked rather than evidence of code-test failure.

NODE-68 must remain Draft / RELEASE BLOCKED until a runner actually executes its Recovery Contract and the required production-like drills above are recorded.

## 8. Production-control boundary

The local Compose recovery profile is an executable recovery harness, **not** a production backup architecture. It intentionally uses local named volumes and a local-only PostgreSQL network policy.

NODE-72 must freeze the production provider-specific implementation for:

- encrypted backup storage;
- immutable/deletion-protected retention;
- backup account/project separation;
- cross-region policy where required;
- network/IAM scoping;
- backup access audit;
- scheduled backup/restore automation and retention cost.

## 9. Acceptance mapping

| NODE-68 acceptance item | Current state |
|---|---|
| PostgreSQL PITR/restore verified | Harness implemented; runtime drill pending |
| Object version/recovery verified | Harness implemented; runtime drill pending |
| Redis/Broker loss rebuildable | DB truth/runbook defined; destructive drill pending |
| AgentRun restart can resume/reconcile | Planner/runbook defined; runtime drill pending |
| Bad deploy rollback runbook tested | Runbook defined; drill pending |
| RPO/RTO measured rather than advertised | Local measurement instrumentation implemented; production measurement pending |

## 10. Release conclusion

```text
SOURCE BASELINE: IMPLEMENTED
LOCAL DR HARNESS: READY TO EXECUTE
PRODUCTION-LIKE RESTORE EVIDENCE: MISSING
PRODUCTION RPO/RTO EVIDENCE: MISSING
NODE-68 RELEASE STATUS: BLOCKED
```

NODE-69 Performance may proceed independently from this branch lineage, but NODE-68 must not be marked complete or release-approved until the missing evidence is closed.
