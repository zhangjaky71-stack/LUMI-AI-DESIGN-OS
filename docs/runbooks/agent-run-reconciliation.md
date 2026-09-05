# Runbook — Agent Run / Task Reconciliation

Owner: Agent Platform / Workflow  
Invariant: **resume from durable business/checkpoint state; never recreate a run by guessing from UI/queue state.**

## Trigger

Use after Agent Runtime restart, worker/broker loss, database restore, region failover, provider timeout/outage, or whenever stale RUNNING/WAITING Agent/Task state exists.

## Inventory

```bash
export LUMI_RECOVERY_DATABASE_URL='postgresql://...'
bash scripts/recovery-workload-report
```

For protected item-level analysis:

```bash
LUMI_RECOVERY_INCLUDE_IDS=1 bash scripts/recovery-workload-report
```

Relevant durable facts:

- `agent_runs` + `agent_run_control`: graph key/version/config/thread/checkpoint/control status.
- `tasks`: status, lease/heartbeat, retry timing, wait reason, external ref.
- `task_attempts`: logical operation key, attempt outcome/cost.
- `idempotency_operations`: operation state, lease, provider request ID, ambiguity.
- `provider_requests` and Cost Ledger: external/paid evidence.

## Decision order

Always evaluate side effects before scheduling work.

1. **Ambiguous paid operation**: MANUAL REVIEW; set/keep automatic retry disabled.
2. **Provider/external request exists**: reconcile native provider status using `provider_request_id`/external ref before any retry.
3. **WAITING_USER / approval interrupt**: preserve the wait; do not auto-approve or convert to runnable.
4. **WAIT_EXTERNAL**: reconcile external system; do not reset to pending merely because a worker restarted.
5. **INTERRUPTED with durable checkpoint**: resume the exact checkpoint/thread using the recorded graph/config version when that version remains supported.
6. **RUNNING with active lease/heartbeat**: no action.
7. **RUNNING stale + checkpoint + no unresolved external/paid side effect**: checkpoint resume is eligible.
8. **Local task with expired lease + no external/paid side effect**: eligible for normal scheduler requeue.
9. **Missing checkpoint, unknown graph version, unknown status, or incompatible schema**: MANUAL REVIEW.

The source policy is encoded in `apps/api/src/lumi_api/recovery/planner.py`; recovery tooling should not invent a looser policy.

## Graph/version compatibility

- Never resume a checkpoint using an arbitrary newer graph definition.
- Prefer the recorded `graph_key`, `graph_version`, `config_version` and thread/checkpoint identity.
- If the recorded graph version is no longer executable, use the documented migration/replay path for that graph or stop for manual intervention.
- A deploy rollback must keep at least the compatibility window required to finish/checkpoint runs created by the previous compatible release.

## Provider uncertainty

Follow `provider-outage.md`. A timeout after request send is **not** proof of failure. Use the provider-native request/job ID and persisted generation/provider request state. If the provider cannot prove the outcome, keep the operation ambiguous and require an operator/business decision rather than paying again automatically.

## Resume validation

After each recovered run/task:

- state transition follows the normal engine/scheduler path;
- no approval boundary was bypassed;
- event IDs/idempotency keys remain stable;
- Cost Ledger contains no duplicate entry for the logical operation;
- produced Artifact/Asset references pass normal validation;
- trace/correlation IDs continue from durable context where supported;
- final user-visible status agrees with DB truth.

## STOP conditions

- any unresolved ambiguous operation;
- provider request exists but cannot yet be reconciled;
- checkpoint/graph version mismatch;
- duplicate Cost Ledger or provider charge evidence;
- cross-tenant mismatch;
- recovery would require editing output/checkpoint payload by hand.

## Exit criteria

- Every non-terminal run/task in incident scope is classified.
- Safe local work resumes through normal scheduler/checkpoint machinery.
- WAITING_USER remains waiting for the user.
- External/paid work is reconciled before retry.
- Duplicate paid side effects = 0.
- Resume/reconciliation timing and unresolved manual cases recorded in NODE-68 evidence.
