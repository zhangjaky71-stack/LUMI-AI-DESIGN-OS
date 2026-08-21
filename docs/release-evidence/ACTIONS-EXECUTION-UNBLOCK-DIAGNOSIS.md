# GitHub Actions Execution Unblock Diagnosis

Date: 2026-08-21
Branch: `release-closure-p0`
PR: #135

## Verdict

**Repository source is not currently the primary blocker. GitHub-hosted Actions execution is blocked before runner steps start.**

The current evidence does **not** support changing product/runtime source code to chase the red CI state. The red state is execution-environment evidence only and is neither application failure evidence nor PASS evidence.

## Representative evidence

Current PR head before the first diagnostic commit:

`a0fc3447471bbb6078d36eb0c8e88c1dccd19ca6`

At that head, dozens of unrelated workflows failed on the same commit, including CI, Secret Scan, Database Schema, Auth Integration, Runtime Image Closure Contract, Image Generation, Video Generation, Model Gateway, Staging Acceptance Gate, Production IaC Contract and Final Product Acceptance Gate.

Representative CI run:

- Workflow: `CI`
- Run: `32463886989`
- Attempt 1 first job: `changes` / job `96716295204`
- Result: `failure`
- `steps=null`
- `logs_url=null`

A real single-job rerun was triggered through the GitHub Actions API.

Attempt 2:

- Run remains `32463886989`
- `run_attempt=2`
- first job: `changes` / job `96718569401`
- observed transition: `queued` -> `completed/failure`
- `steps=null`
- `logs_url=null`
- all dependent jobs skipped

The `changes` job is a minimal GitHub-hosted Ubuntu job whose first executable action is `actions/checkout`. Because GitHub reports no steps and no downloadable job log, no repository command, checkout, Python, Node, `uv`, Docker, Terraform, database command, or application code is evidenced as having started.

## Post-account-change rerun

After the account-side billing/budget settings were adjusted, the current-head minimal `CI / changes` job was rerun again:

- source head before isolation experiment: `c0ae64d644b4d159d936cc8aa6b3a798ceb2bf25`
- workflow run: `32465520731`
- rerun job: `96722114616`
- observed transition: `queued` -> `completed/failure`
- `steps=null`
- `logs_url=null`

Therefore the account-side change did not yet produce a runnable GitHub-hosted VM for the repository.

## Runner-label isolation experiment

A temporary diagnostic workflow was committed at `66622207ddc40f8499e9f53834605998bf628bd8` with two independent jobs. Each job had exactly one shell `echo` step and used no checkout, no third-party Action, no dependency installation, no repository code, no secrets and no external service.

Workflow run: `32465958920`

Results:

- `ubuntu-latest` / job `96722467731`: `completed/failure`, `steps=null`, `logs_url=null`
- `ubuntu-24.04` / job `96722467435`: `completed/failure`, `steps=null`, `logs_url=null`

Both standard GitHub-hosted Linux labels are supported for private repositories according to GitHub's runner documentation. The identical pre-step failure therefore rules out an `ubuntu-24.04`-specific label problem.

The temporary diagnostic workflow is removed after recording this result; it is not part of the intended release workflow surface.

## Scope reduction

The following explanations are now directly ruled out for the observed zero-step failures:

- application source code;
- Python/Node/`uv`/Docker/Terraform execution;
- checkout or third-party Action failure;
- repository secrets;
- dependency installation;
- an `ubuntu-24.04`-specific runner label issue;
- job-level shell commands, because the shell never starts.

GitHub Actions is recognized and the workflow/job objects are created successfully, so this is also not being treated as an invalid-workflow parse failure.

The remaining blocker class is account/repository GitHub-hosted runner execution eligibility/allocation, with billing, included quota and hard budget controls still the highest-probability causes.

The affected repository is private and owned by the personal account `zhangjaky71-stack`.

GitHub's current billing documentation states that private repositories consume the owner's GitHub-hosted Actions allowance. If the included quota is exhausted and no valid payment method is available, additional GitHub-hosted usage is blocked. With a valid payment method, one or more exhausted budgets with `Stop usage when budget limit is reached` can still block usage.

No recent matching GitHub Actions/billing warning email was found in the currently connected Gmail account. Absence of such email is **not** treated as proof that quota/budget/payment is healthy, because alerts can be disabled, sent to another billing address, or omitted for a particular account state.

## Highest-priority account checks

Inspect the personal account, not repository source:

1. **Settings -> Billing & licensing -> Usage**: confirm GitHub Actions included usage and metered usage state.
2. **Settings -> Billing & licensing -> Budgets and alerts**: inspect every budget that applies to Actions, including overlapping product/repository budgets.
3. Confirm the payment method is valid and usable for metered Actions usage.
4. Confirm no applicable budget is exhausted with `Stop usage when budget limit is reached` enabled.
5. Confirm the account/repository is allowed to use standard GitHub-hosted runners.

If a payment method was just added or repaired, successful runner allocation—not the UI save itself—is the acceptance criterion.

## Acceptance test after account unblock

Re-run a minimal job first.

Execution environment is considered unblocked only when the job exposes real steps/logs and a shell or checkout actually begins. A red job with actual steps is materially different from the current zero-step red state and can then be diagnosed as a real repository/test failure.

Once the minimal job starts executing, proceed in this order:

1. canonical `uv.lock` regeneration workflow;
2. exact workspace lock validation and frozen sync;
3. six-runtime image build / provenance / SBOM / attestation;
4. PostgreSQL and runtime integration evidence;
5. NODE-71 Staging acceptance;
6. NODE-72 Production promotion;
7. NODE-73 Final Acceptance.

## Release verdict

**KEEP NODE-73 FINAL ACCEPTANCE BLOCKED.**

Current zero-step GitHub Actions failures are execution-environment blockers, not product PASS and not source/application failure evidence.
