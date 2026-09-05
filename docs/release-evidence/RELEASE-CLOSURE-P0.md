# Release Closure P0 Evidence

Date: 2026-08-19
Branch: `release-closure-p0`
Base: `node-73-final-acceptance-release`
Draft PR: `#135`
Scope: close code-addressable P0 blockers identified by NODE-73 Final Acceptance without inventing a new NODE.

## Executive status

`release-closure-p0` is **not Final Acceptance and not Production GO-LIVE approval**.

This branch now contains code/IaC remediation for the major code-addressable NODE-73 blockers:

1. one platform-wide Provider USD hard stop backed by the canonical NODE-27 ledger;
2. NODE-20 durable paid-side-effect crash protection before Provider network calls;
3. a real private Hosted Model Gateway service boundary with internal authentication, logical model profiles and Deep Agents HTTP binding;
4. explicit Production/Staging Sandbox egress isolation;
5. release-contract hardening so NODE-71 freezes the exact six immutable RC images and their critical build provenance, NODE-72 must deploy those exact digests, and the Production first-day Provider limit cannot exceed `$100`.

NODE-73 remains **BLOCKED** because auditable runtime evidence is still missing. The checked-in `uv.lock` is stale, GitHub-hosted jobs continue to fail before any step executes, the six runtime images have not been built/promoted as one accepted RC set, and Production-like Staging / Production / rollback / DR evidence is still absent.

## P0-1 — platform-wide Provider USD/day hard stop

Status: **IMPLEMENTED IN CODE / LIVE POSTGRESQL + DEPLOYED IMAGE PROOF PENDING**

### Canonical accounting architecture

Release Closure reuses NODE-27's existing financial truth and does **not** create a second Provider ledger.

Canonical facts remain:

- `cost_ledger` — append-only actual Provider cost / adjustment / reversal facts;
- `cost_reservations` — pre-Provider estimated-cost occupancy;
- existing NODE-27 usage, quota and reconciliation tables/runtime.

Early Release Closure drafts that introduced parallel `provider_cost_*` tables/functions were removed. The final branch extends the existing NODE-27 boundary only.

### Platform policy

Alembic revision:

- `apps/api/alembic/versions/0018_platform_provider_cost_guard.py`

creates singleton `platform_provider_cost_guard` with:

- `policy_key = 'platform'`;
- USD/UTC-day semantics;
- default cap `$100.00000000`;
- `enabled = true`;
- `fail_closed = true`;
- database constraint `daily_cap_usd > 0 AND daily_cap_usd <= 100.00000000`.

The `$100` ceiling is therefore a schema maximum, not merely a default. `lumi_app` has SELECT-only access and cannot raise, disable or delete the policy at runtime.

The policy is mapped into SQLAlchemy metadata through `PlatformProviderCostGuard`, so the normal ORM schema-drift gate can validate it after migration.

### Cross-process / cross-organization hard stop

`PlatformGuardedCostGateway` wraps the canonical `PostgresCostGateway`.

Before a paid reservation it:

1. obtains PostgreSQL advisory transaction lock `cost-budget:platform:provider-usd:utc-day`;
2. reads the fail-closed singleton policy;
3. calculates current UTC-day Provider spend from canonical `cost_ledger` across all organizations;
4. calculates active USD reservations from canonical `cost_reservations` across all organizations;
5. rejects when `spent + active + requested > cap`;
6. while still holding the platform lock, delegates to NODE-27's canonical `PostgresCostGateway.reserve()`.

Commit/release are serialized against the same platform lock. If a Provider has already accepted work and actual cost exceeds the estimate, the sunk fact is committed rather than hidden; later reservations then fail closed.

### NODE-20 paid-side-effect crash barrier

Release Closure found a separate exactly-once failure mode: a Provider could accept a paid request and the process could crash before `provider_request_id` was durably bound. A stale lease would then previously be able to choose `EXECUTE` again.

Alembic revision:

- `apps/api/alembic/versions/0019_side_effect_provider_attempt_barrier.py`

adds the durable `provider_attempt_started_at` barrier and the ORM metadata was updated with the same column.

The NODE-20 state machine now requires:

- mark Provider attempt started **before** the network side effect;
- stale lease + `provider_request_id` => reconcile path;
- stale lease + attempt-started marker but no Provider request id => persistent `AMBIGUOUS`, never execute again;
- only an explicitly classified `DeliveryState.NOT_ACCEPTED` outcome can clear the attempt barrier and permit a safe retry;
- generic retryable, `UNKNOWN`, or `ACCEPTED` outcomes after attempt start cannot clear the barrier.

`apps/api/tests/integration/test_idempotency_provider_attempt_barrier.py` and the NODE-20 failure-injection workflow encode the crash-after-attempt-start drill on PostgreSQL.

### Hosted paid guard

`PostgresModelPaidInvocationGuard` adapts Model Gateway paid calls to the NODE-20 side-effect gateway. Hosted composition constructs this guard internally; `build_hosted_model_gateway()` does not expose `paid_guard` or `paid_stream_guard` injection parameters.

A successful `ModelResult` is durably replayable without calling the Provider again. Explicit `NOT_ACCEPTED` preserves safe retry semantics, while unknown delivery is persisted fail-closed. Streaming remains intentionally disabled in Hosted composition until an equivalent durable stream guard exists.

### Model Gateway cost binding

`PostgresModelCostAccounting` uses `PlatformGuardedCostGateway`. The `lumi_model_gateway` package itself remains database-neutral behind its cost port.

Hosted composition root:

- `apps/api/src/lumi_api/model_gateway_runtime.py`

fixes the financial path to:

`LedgerBudgetGuard(PostgresModelCostAccounting(database_dsn))`

and fixes the paid-side-effect path to `PostgresModelPaidInvocationGuard`.

The Hosted factory does not accept an injectable request-local budget guard or paid guard.

### Provider credential boundary

Staging and Production IaC make `model-gateway` the only deployment unit holding Provider credentials:

- `agent-runtime` does not receive model Provider credentials;
- `worker-media` does not receive media Provider credentials;
- `model-gateway` receives `LUMI_MODEL_PROVIDER_SECRET` and `LUMI_MEDIA_PROVIDER_SECRET`;
- `model-gateway` receives `LUMI_DATABASE_URL` for durable NODE-20/NODE-27 state;
- `agent-runtime` and `worker-media` receive only private Model Gateway URL + internal HMAC secret;
- public API does not receive that internal invocation secret.

`validate_production_iac_contract.py` and release-security tests enforce this least-privilege topology in Staging and Production.

### Deep Agents cannot bypass the Hosted Model Gateway

Agent Runtime now includes a LangChain-compatible `ModelGatewayChatModel` that converts Deep Agents chat/tool turns into the provider-neutral Model Gateway HTTP contract.

Key invariants:

- Provider credentials never enter Agent Runtime;
- the client uses `HttpModelGatewayClient` over the private service URL with HMAC service authentication;
- tool definitions, tool calls and tool results stay provider-neutral outside the Provider adapter;
- each model turn derives a stable child operation UUID from parent operation + logical profile + semantic inputs, so same-turn retries replay while a changed tool loop gets a distinct NODE-20 idempotency identity;
- root budget is propagated into subagent model context;
- logical `model_profile` is a hard routing constraint, and unknown profiles fail `NoRoute` instead of silently selecting another model.

Production composition is `HostedDeepAgentRuntimeFactory`. Its constructor deliberately exposes no `models=` parameter and internally constructs `HttpProfileModelProvider.from_env()`. Static AST contracts and a unit signature test fail if a model-provider injection point is reintroduced.

### PostgreSQL acceptance

The NODE-27 / NODE-20 / NODE-22 suites are designed to prove on real PostgreSQL that:

- even the migration/admin role cannot set the Provider hard ceiling above `$100`;
- six concurrent `$0.10` reservations split across two organizations compete on one platform lock and exactly three fit under `$0.30` incremental headroom;
- disabled policy fails closed;
- actual Provider cost may exceed an already-reserved estimate but is still recorded;
- post-overshoot reservations are denied;
- runtime role cannot mutate the platform policy;
- crash after Provider-attempt start cannot produce a second execution;
- successful paid calls replay without a second Provider call;
- `NOT_ACCEPTED` can retry safely;
- `UNKNOWN` remains persistently blocked.

These are acceptance definitions only until a trusted runner actually executes them.

### Production release limit alignment

`production/deployment/manifest-template.json` now defaults `daily_provider_spend_usd` to `100`.

`production-deployment-gate.py` requires `0 < daily_provider_spend_usd <= 100`, and the contract includes a `$100.01` negative drill that must BLOCK.

The deployment manifest can choose a stricter value below `$100`, but cannot advertise or authorize a higher first-day Provider envelope than the durable database boundary.

## P0-2 — Production Sandbox egress isolation

Status: **IMPLEMENTED IN IAC / TERRAFORM APPLY + LIVE PROBE PENDING**

### Existing inner boundary retained

`sandbox-runtime` already executes child Docker work with `--network none`; Release Closure keeps that inner deny-all execution boundary.

### Shared IaC boundary

- shared app Security Group is identity/ingress only and grants no public egress;
- `app_internet_egress` grants explicit Internet egress to non-Sandbox services;
- `sandbox_egress` allows only private VPC traffic plus TCP/443 to the AWS-managed S3 prefix list;
- `sandbox_egress` contains no `0.0.0.0/0` rule;
- PrivateLink interface endpoints exist for `ecr.api`, `ecr.dkr`, `logs`, and `secretsmanager`;
- ECS composition attaches restricted egress to `sandbox-runtime` and explicit Internet egress to normal services;
- Staging and Production use the same topology.

Static IaC/release-security tests encode these invariants so a later change cannot silently reattach public egress to Sandbox.

### Still required for acceptance

- run `terraform fmt -check`, `terraform validate`, and Production-like Staging `terraform plan` with the pinned provider;
- apply to Production-like Staging;
- launch the real `sandbox-runtime` image;
- prove required Redis/RabbitMQ/S3/internal control-plane traffic remains functional;
- prove arbitrary public DNS/IP HTTPS and raw TCP egress are denied;
- prove ECR pull, CloudWatch Logs and Secrets Manager work through PrivateLink;
- archive VPC Flow Logs and task probe output.

## P0-3 — canonical root `uv.lock`

Status: **NOT CLOSED**

The workspace/dependency graph has evolved beyond the checked-in lock. The branch intentionally does not hand-edit `uv.lock`.

The canonical repair remains:

```bash
uv lock
uv sync --all-packages --frozen
```

using Python 3.12 and normal registry access, followed by Ruff, Pyright, pytest and the PostgreSQL acceptance suites.

This blocker is now even more important because the real `services/model-gateway/Dockerfile` executes:

```bash
uv sync --all-packages --frozen --no-dev
```

Therefore a stale canonical lock blocks honest Model Gateway image construction rather than being bypassed in the Docker recipe.

Cost Ledger, NODE-71 Staging Acceptance and Final Product Acceptance workflows consistently use `--all-packages --frozen` where the full workspace is being accepted.

## P0-4 — exact RC image identity, executable Model Gateway and provenance

Status: **SOURCE BUILD/ENTRYPOINT CONTRACT IMPLEMENTED / REAL SIX-IMAGE BUILD + PROMOTION EVIDENCE PENDING**

### NODE-71 freezes the real image set

`staging/acceptance/evidence-template.json` requires, for all six runtime units:

- immutable `@sha256` image digest;
- source `git_sha`;
- build recipe reference;
- executable entrypoint;
- SBOM reference;
- provenance reference;
- source-path list.

`staging-acceptance-gate.py` validates exactly six image/provenance entries and freezes the normalized `container_image_set` into the NODE-71 decision hash.

### Model Gateway executable source closure

A real source-level Model Gateway service now exists:

- `services/model-gateway/Dockerfile`;
- `apps/api/src/lumi_api/model_gateway_cli.py`;
- `apps/api/src/lumi_api/model_gateway_service.py`;
- `apps/api/src/lumi_api/model_gateway_bootstrap.py`.

The Docker recipe:

- uses Python 3.12;
- performs frozen all-workspace install with no dev dependencies;
- runs as non-root UID/GID 10001;
- exposes port 8080;
- starts `python -m lumi_api.model_gateway_cli`.

The CLI starts the FastAPI factory on port 8080. The service exposes `/health/live`, `/health/ready`, `/version` and signed `/internal/v1/models/invoke`. Readiness checks both the NODE-20 provider-attempt barrier and NODE-27 platform Provider-cost guard and returns not-ready when those durable prerequisites are missing or invalid.

This closes the previous **source-code** gap where Model Gateway was only a library. It does **not** prove that a container image has actually built, started, passed health checks or been promoted.

### NODE-71 now requires critical Hosted sources in Model Gateway provenance

The Model Gateway provenance source list must include all of:

- `services/model-gateway`;
- `apps/api/src/lumi_api/model_gateway_runtime.py`;
- `apps/api/src/lumi_api/model_gateway_bootstrap.py`;
- `apps/api/src/lumi_api/model_gateway_service.py`;
- `apps/api/src/lumi_api/model_gateway_cli.py`;
- `apps/api/src/lumi_api/model_paid_guard.py`;
- `apps/api/src/lumi_api/idempotency/gateway.py`;
- `apps/api/src/lumi_api/costs/model_gateway_adapter.py`.

Thus a model-gateway image that omits the executable HTTP service, Provider bootstrap, NODE-20 paid guard/idempotency state machine, NODE-27 cost adapter or Hosted composition cannot receive NODE-71 PASS merely because its Git SHA matches.

`validate_staging_acceptance_contract.py` runs negative drills that remove critical executable/paid/idempotency/cost source paths and requires BLOCK.

### NODE-72 cannot swap images after Staging acceptance

`production-deployment-gate.py` requires exact equality between Production manifest images and `NODE-71 decision.container_image_set.images`.

A different but syntactically valid `@sha256` digest is rejected. Final Acceptance additionally requires `PROD-02`: exact Staging-accepted immutable digests deployed through the controlled Production workflow and canary.

### Real image build/promotion remains unresolved

The remaining gap is now narrower and explicit:

- a Model Gateway Dockerfile/entrypoint exists, but no trusted run has successfully built and started that image on the current RC;
- the stale canonical `uv.lock` must be repaired before the frozen Docker build can honestly succeed;
- no six-runtime build/promotion pipeline has yet produced one auditable six-digest RC set;
- no SBOM/provenance attestations for the actual six built images have been archived;
- no NODE-71 Production-like Staging decision has frozen those real six images;
- no NODE-72 Production deployment has proved the same exact digests.

This remains a P0 blocker.

## Hosted CI evidence status

Latest sampled PR #135 runs at head `6e40e5657d700504dfa473b48cd44b3bbe3992a2` still fail before executing steps:

- Model Gateway run `32203009437`:
  - `source-contract` job `95920536640` = failure, `steps=null`, `logs_url=null`;
  - `model-gateway` and `hosted-paid-guard-postgres` = skipped.
- Deep Agents Runtime run `32203009337`:
  - `deep-contract` job `95920536223` = failure, `steps=null`, `logs_url=null`;
  - `deep-quality` and `deep-stack` = skipped.
- Final Product Acceptance run `32203009418`:
  - `canonical-lock-gate`, `source-contract` and `contract-gate` = failure with no step data;
  - `final-decision` = skipped.

No checkout, Python, `uv`, test, Terraform or application command is evidenced as having executed in those jobs. These red runs therefore cannot be interpreted as application-test failures, and they also cannot count as PASS evidence. The failure pattern remains consistent with the existing GitHub-hosted runner/account/scheduling/billing blocker.

## Remaining live blockers

Before NODE-73 can change from BLOCKED, auditable PASS evidence is still required for:

- GitHub-hosted runner execution recovery or equivalent trusted CI;
- canonical `uv lock` + `uv sync --all-packages --frozen`;
- Alembic `0018` + `0019`, ORM drift validation, NODE-20 crash barrier and NODE-27/22 PostgreSQL acceptance on real PostgreSQL;
- Model Gateway container build/start/health/invoke proof from the frozen Docker recipe;
- Terraform format/validate/plan/apply in Production-like Staging;
- live Sandbox egress allow/deny probes;
- a real six-runtime image build/promotion process;
- SBOM/provenance and exact digest capture for all six runtime images;
- proof that Agent Runtime and Worker Media consume the private Model Gateway in the deployed environment rather than Provider credentials;
- NODE-68/69/70/71/72 cloud/RC evidence;
- Production smoke/canary/rollback and DR evidence;
- final operational approvals/handoff.

## Release decision

Current decision: **KEEP NODE-73 FINAL ACCEPTANCE BLOCKED**.

PR #135 remains a Draft remediation layer. Do not mark it as Final Acceptance, do not declare Production GO-LIVE, and do not change the NODE-73 verdict until all remaining lock, CI, PostgreSQL, Terraform, Staging, image-build/provenance, Production and DR gates are auditable and passed.
