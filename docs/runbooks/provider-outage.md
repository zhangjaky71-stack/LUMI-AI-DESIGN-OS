# Runbook — Model / External Provider Outage

Owner: Model/Tool Platform  
Primary invariant: **timeout/connection loss after send does not prove the provider did not execute the request.**

## Trigger

Use for model/image/video/SaaS provider outage, sustained timeout/rate-limit, unknown asynchronous job status, provider response loss, or provider region incident.

## Containment

1. Disable or sharply reduce new traffic to the affected provider through normal routing/circuit-breaker controls.
2. Preserve provider-native request/job IDs, operation IDs, attempt records and trace refs.
3. Do not delete `provider_requests`, `idempotency_operations`, generation rows or Cost Ledger evidence.
4. Stop automatic retry for operations that may have crossed the provider boundary.

## Classification

- Request definitely rejected before send / no provider request ID and local policy proves no side effect -> normal retry/fallback may be safe.
- Provider returned a final failure -> apply the recorded retryable/final policy.
- Provider request/job ID exists with non-final local status -> query/reconcile provider state first.
- Local process timed out/crashed after send and provider outcome cannot be proven -> mark/keep `ambiguous`; **do not automatically send another paid request**.
- Provider reports success but callback/result was lost -> persist/recover the existing provider result, then continue normal validation/artifact flow without a second generation request.

## Reconciliation procedure

1. Scope affected rows by provider, incident window and non-terminal operation status.
2. For each provider-native request/job ID, use the provider's status/retrieve API when supported.
3. Compare provider result with `provider_requests`, generation state, task attempt and Cost Ledger.
4. Apply a single deterministic outcome:
   - reconcile success and ingest the existing result;
   - reconcile final failure;
   - remain ambiguous/manual when provider evidence is insufficient.
5. Resume dependent Agent/Task work through `agent-run-reconciliation.md` only after external state is settled.
6. Re-enable traffic gradually; keep fallback/provider routing bounded by budget/capability policy.

## Cost safety

- Never infer “not charged” from an HTTP timeout.
- Never create a new idempotency key to bypass an ambiguous operation.
- Cost Ledger is append-only/accounting truth; corrections use explicit reversal/reconciliation semantics, not row edits.
- Any confirmed duplicate paid side effect is an incident/STOP SHIP condition.

## STOP conditions

- Provider cannot return authoritative status and the request may have executed.
- Native request ID is missing for a request believed to have been sent.
- Local Cost Ledger/provider billing disagree materially.
- Recovery path requires another paid request merely to discover whether the first succeeded.

## Exit criteria

- Incident-scope provider operations are final or explicitly manual/ambiguous.
- No automatic retries remain for ambiguous operations.
- Duplicate paid side effects = 0 or incident escalated.
- Backlog/retry rates return to normal.
- Provider incident start/end and reconciliation duration recorded.
