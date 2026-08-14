# NODE-36 Hosted CI Evidence

> PR: #36 — NODE-36: Knowledge Engine  
> Branch: `node-36-knowledge-engine-release`  
> Classification: **IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL / not COMPLETE**

## Hosted run

```text
workflow: Knowledge Engine
run_id: 31774976122
job: knowledge-contract
job_id: 94688425350
head_sha: 98c40ee0131defc4f7cecd402dc88a248b2b8a02
status: completed
conclusion: failure
```

## Runner evidence

GitHub job metadata returned:

```text
steps: []
runner_id: 0
runner_name: ""
runner_group_id: 0
runner_group_name: ""
```

No workflow step was executed and no runner was allocated.

## GitHub annotation

GitHub Actions returned the failure annotation:

> The job was not started because recent account payments have failed or your spending limit needs to be increased. Please check the 'Billing & plans' section in your settings

## Interpretation

This is an external GitHub account/billing/spending-limit blocker before runner allocation.

It is **not** evidence that NODE-36 compile, unit, Ruff, Pyright, PostgreSQL integration, migration, or schema-drift gates failed.

Those gates remain unexecuted on hosted Actions, so NODE-36 must not be marked COMPLETE.
