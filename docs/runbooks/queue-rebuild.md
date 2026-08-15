# Runbook — RabbitMQ Rebuild / Event Replay

Owner: Platform / Messaging  
Core invariant: **RabbitMQ is transport, PostgreSQL is business truth.** Never infer paid/business completion from queue presence or absence.

## Trigger

Use for broker data loss, corrupted Rabbit volume, topology rebuild, mass consumer failure, or region failover with an empty/new broker.

## Before mutation

1. Stop/fence publishers and consumers if the broker is producing duplicate/unknown behavior.
2. Preserve broker logs/definitions if available.
3. Confirm PostgreSQL is healthy and authoritative. If DB was also restored, finish `db-restore.md` first.
4. Inventory recovery work:

```bash
export LUMI_RECOVERY_DATABASE_URL='postgresql://...'
bash scripts/recovery-workload-report
```

Use `LUMI_RECOVERY_INCLUDE_IDS=1` only in a protected operator terminal when item-level reconciliation is required.

## Rebuild

1. Provision the broker from version-controlled topology/config, not from guessed queues.
2. Keep workers stopped while topology, credentials, vhost permissions, DLX/DLQ and durability are verified.
3. Reconcile `idempotency_operations` before replay:
   - `ambiguous` -> MANUAL REVIEW, no automatic retry.
   - `in_progress` with `provider_request_id` -> provider reconciliation first.
   - expired `in_progress` without proof no request was sent -> MANUAL REVIEW.
   - `new` / safe `failed_retryable` without provider request -> eligible for normal scheduler/requeue path.
4. Replay unpublished `outbox_events` through the **normal outbox publisher**, preserving the original outbox/event ID and schema version.
5. If broker loss may have occurred after DB marked an event published but before consumers committed work, replay the bounded incident window with the **same event IDs**. Existing `inbox_events` `(consumer,event_id)` uniqueness is the duplicate-consumption guard.
6. Do not synthesize new event IDs to “force” processing; that bypasses inbox idempotency.
7. Review durable `dead_letter_records` separately. Replay only after root cause is fixed and the owning side effect is proven safe.
8. Start consumers in small batches. Watch error rate, DLQ growth, idempotency conflicts and Cost Ledger/provider activity.

## Task/Agent handoff

After event transport is healthy, run `agent-run-reconciliation.md`. Queue recovery is not permission to reset every RUNNING task to PENDING.

## Redis note

Redis loss is rebuildable. Recreate cache/session-derived indexes from canonical stores where designed; use conservative defaults for rate limiting while counters warm. Do not restore stale Redis state merely to make dashboards look normal.

## STOP conditions

- Database truth is unavailable/uncertain.
- `ambiguous` paid operations are being auto-retried.
- Replayer generates new IDs for historical events.
- Consumer inbox/idempotency protection is disabled.
- DLQ grows rapidly after restart.
- Provider/Cost Ledger signals show duplicate paid side effects.

## Exit criteria

- Broker topology healthy.
- Unpublished outbox backlog drains through normal publisher.
- Incident replay window processed with stable event IDs.
- DLQ is stable and explained.
- Paid/provider ambiguous work is reconciled, not blindly retried.
- Queue rebuild timing and data-loss/replay window recorded in NODE-68 evidence.
