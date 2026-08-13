# NODE-19 Acceptance — Queue & Event Runtime

Status: **IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL**

## Scope delivered

- [x] Job and Domain Event semantics are separate.
- [x] RabbitMQ `lumi.jobs` / `lumi.domain` / `lumi.dlx` topology is codified and repeatable.
- [x] Media queues are isolated for image, video, export, and asset processing.
- [x] Celery routes sample/media runtime tasks to explicit queues.
- [x] Broker payload guard blocks binary, large payloads, and secret-like fields.
- [x] Retry policy classifies transient/permanent/cancelled errors and requires reconciliation for video retries.
- [x] NODE-20 late-ACK boundary is enforced (`acks_late=false`).
- [x] Outbox dispatcher uses `FOR UPDATE SKIP LOCKED`, publish attempts, and post-publish marking.
- [x] Inbox dedupe uses `(consumer,event_id)` and handler effect is committed in the same DB transaction.
- [x] Permanent consumer failures reject without requeue and persist `dead_letter_records` for Admin visibility.
- [x] Existing `tasks` / `asset_validation_runs` remain the business job-state sources of truth.

## Validation performed in this implementation session

- [x] Python source syntax compiled successfully for all newly authored Python files.
- [x] 100-character source-line audit completed after corrections.
- [x] Static NODE-19 contract validator authored.

## Validation pending hosted runner

- [ ] Frozen `uv sync --all-packages --frozen` on GitHub-hosted runner.
- [ ] Ruff / Pyright / full pytest suite on hosted runner.
- [ ] Alembic upgrade + ORM drift check for `0008_queue_event_runtime`.
- [ ] Live RabbitMQ Celery delivery.
- [ ] Live Outbox → RabbitMQ → Inbox duplicate suppression.
- [ ] Live permanent failure → RabbitMQ DLQ + `dead_letter_records`.
- [ ] Worker crash/redelivery failure injection.

The repository's GitHub Actions jobs are currently unable to start because of the previously observed account billing/spending-limit blocker. This node must **not** be marked COMPLETE until the required hosted/integration gates actually execute green.

## Decision

NODE-19 is implementation-complete enough to open as a stacked PR on NODE-18, but remains **not COMPLETE**. Next engineering node after NODE-19 gates is NODE-20 — Idempotency & Side Effects.
