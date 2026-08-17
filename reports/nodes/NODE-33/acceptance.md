# NODE-33 Acceptance — Task Graph & Scheduler V1

Status: **IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL**

## Implemented

- [x] Immutable content-hashed `TaskGraphDefinition` and deterministic graph/task IDs.
- [x] DAG validation: unique keys, missing dependency rejection, self-edge rejection, cycle rejection.
- [x] Exact `agent@version` and `context-bundle://...` pins for AGENTIC tasks.
- [x] Deterministic READY promotion with ALL_SUCCESS / ALL_TERMINAL / ANY_SUCCESS joins.
- [x] Priority ordering, graph max parallelism, and concurrency-group limits.
- [x] Transaction/CAS store contract plus deterministic in-memory reference adapter.
- [x] Lease owner + fencing token + expiry + heartbeat.
- [x] Lease-expiry reclaim with provider-reconciliation evidence.
- [x] Stable logical operation key across retries.
- [x] Deterministic retry backoff and `retry_not_before`.
- [x] FAIL_FAST and CONTINUE failure propagation.
- [x] Cooperative pause/resume/cancel semantics.
- [x] WAITING_USER / WAITING_EXTERNAL suspend and resolution.
- [x] Graph/task budget fail-stop accounting boundary.
- [x] Private-reasoning-safe TaskGraph events.
- [x] Structural NODE-28 `TaskGraphPort` adapter with frozen route vocabulary.
- [x] NODE-29 `ScheduledAgentTaskRequestResolver` with claimed-task and exact-pin validation.
- [x] Dedicated NODE-33 workflow, runtime design document and gap ledger.

## Local executable validation

The isolated compatibility harness completed:

- formal NODE-33 pytest contract suite: **14 passed**;
- Python `compileall`: **PASS**;
- line-length check against the repository 100-character setting: **PASS**;
- NODE-29 scheduled-request adapter compatibility case: **PASS** using a local compatibility stub matching the
  current Deep Runtime contract shape.

Local Ruff is **not claimed PASS** because Ruff is not installed in the available execution environment. The hosted
workflow installs Ruff and remains authoritative when GitHub can allocate a runner.

## Hosted validation

The repository's current Agent chain is affected by an external GitHub Actions account billing/spending-limit runner
allocation condition. A hosted run is not considered a code failure when the job shows `runner_id=0` and `steps=[]`.
NODE-33 must be reclassified from `BLOCKED_EXTERNAL` only after a runner actually starts and executes its steps.

## Not COMPLETE until

1. the dedicated NODE-33 hosted workflow actually receives a runner and executes compile/Ruff/pytest/gap parsing;
2. repository CI/security gates execute green;
3. the durable multi-replica TaskGraph store gap is closed or explicitly superseded;
4. production worker composition claims tasks before execution and reports completion/failure/suspension back through
   the scheduler;
5. paid provider work uses the authoritative cost reservation/idempotency boundary before provider acceptance;
6. the stacked dependency chain is resolved in merge order.

The old draft PR #33 was built on a different historical NODE-32 Recipe Engine branch. This current NODE-33 is a new
stacked implementation on `feat/node-32-context-compiler`; no completion status is inherited from that old branch.
