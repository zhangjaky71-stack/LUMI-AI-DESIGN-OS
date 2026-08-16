# Production Rollback and Alert Delivery Drills

Status: **SOURCE_IMPLEMENTED / VALIDATION_PENDING**

This runbook closes source-level gaps required by NODE-73. It does **not** claim that production rollback, alarm firing, machine delivery, or human on-call delivery has executed successfully.

## 1. Safety model

Production release safety is intentionally split into independent controls:

1. deployment rollback enforcement;
2. immutable pre-deployment rollback evidence;
3. controlled post-promotion rollback drill;
4. alarm firing/recovery;
5. durable machine-delivery evidence;
6. human on-call delivery and acknowledgement.

A green Terraform plan or a source-only runbook is not runtime evidence.

## 2. Deployment rollback enforcement

`infra/iac/modules/compute/main.tf` already provides two deployment rollback paths:

- public services use ECS `CANARY` deployment configuration with the ALB green-target 5xx and unhealthy-host CloudWatch alarms and `rollback=true`;
- non-public services use the ECS deployment circuit breaker with `rollback=true`.

`infra/iac/modules/compute/alerting.tf` adds the notification route without replacing those rollback controls.

## 3. Deployment alert route

The source route is:

```text
Public canary 5xx / unhealthy alarms
        -> CloudWatch composite deployment alarm
        -> encrypted SNS deployment-alert topic
        -> encrypted SQS evidence queue

Non-public ECS deployment circuit-breaker failure
        -> EventBridge SERVICE_DEPLOYMENT_FAILED
        -> encrypted SNS deployment-alert topic
        -> encrypted SQS evidence queue
```

The SNS topic uses a dedicated customer-managed KMS key. Its key policy explicitly permits the AWS service publishers used by this route. The topic policy separately permits CloudWatch/EventBridge publish and preserves account-owner administration.

The SQS subscriber is an **evidence sink**. It proves that a message traversed the AWS alert transport. It is not a substitute for PagerDuty, Slack, email, incident management, or another real human notification endpoint.

Before NODE-73 can pass, Operations must attach the approved human on-call destination to the SNS topic (or an approved downstream integration), fire a controlled alert, and archive proof of human delivery/acknowledgement according to the launch policy.

## 4. Controlled alert delivery drill

Use the protected workflow:

```text
.github/workflows/final-operational-drills.yml
operation = alert-delivery
manifest_path = reports/production-deployments/<deployment-id>/manifest.json
drill_ack = ALERT_DRILL:<deployment-id>
```

The workflow must run under the protected `production` GitHub Environment and assume the exact production role frozen in the deployment manifest.

`scripts/alert-delivery-drill.sh` then:

1. reads the deployed SNS topic and SQS evidence queue from Terraform outputs;
2. creates a unique temporary high-resolution CloudWatch alarm on a synthetic `LUMI/OperationalDrill` metric;
3. writes a healthy baseline and requires the alarm to reach `OK`;
4. writes a controlled breaching metric and requires `ALARM`;
5. consumes the exact SNS notification from the SQS evidence queue and records its AWS message id;
6. restores the healthy metric and requires `OK`;
7. consumes the recovery notification and records its message id;
8. deletes the temporary alarm in a cleanup trap;
9. writes `alert-delivery.json` only after the full firing/recovery route succeeds.

This drill does not call a paid AI provider and does not intentionally break application traffic.

Required archived evidence:

```text
final-operational-drill-alert-delivery-<workflow-run-id>/alert-delivery.json
CloudWatch alarm history for the drill alarm
SNS/SQS resource configuration
approved human notification delivery/ack evidence
```

## 5. Freeze the rollback target before every production mutation

`Deploy Production` now initializes the current production application state and runs:

```bash
bash scripts/capture-ecs-deployment-state.sh \
  infra/iac/environments/production/app \
  reports/production-deployments/runtime/predeploy-ecs-state.json
```

before the pre-deployment RDS snapshot, database migration, or application mutation.

The deployment artifact therefore freezes the last-known-good:

```text
cluster ARN
service name
immutable ECS task definition ARN
service desired/running/pending counts
PRIMARY deployment state
```

The same deployment artifact later contains post-deployment ECS state and production smoke evidence.

### First production bootstrap

A first-ever environment bootstrap has no previous ECS release to roll back to. It therefore cannot satisfy the NODE-73 post-promotion rollback requirement. Final acceptance requires at least one previously verified known-good deployment before the release candidate used for the rollback drill.

Do not weaken the drill by accepting a no-op rollback as final evidence.

## 6. Controlled immutable rollback drill

Use the protected workflow:

```text
.github/workflows/final-operational-drills.yml
operation = rollback
manifest_path = reports/production-deployments/<deployment-id>/manifest.json
deployment_run_id = <the exact Deploy Production workflow run id>
drill_ack = ROLLBACK_PRODUCTION:<deployment-id>:<deployment-run-id>
```

The workflow downloads the exact archived artifact named:

```text
production-deployment-<deployment-id>-<deployment-run-id>
```

and refuses to proceed without both:

```text
predeploy-ecs-state.json
post-deployment ecs-deployment-state.json
```

`scripts/ecs-rollback-to-state.sh` then:

1. validates that the source snapshot itself was a verified steady state;
2. compares live task definitions to the frozen known-good task definitions;
3. refuses a no-op drill unless an explicit non-acceptance troubleshooting override is supplied;
4. validates that every target ECS task definition remains `ACTIVE` before mutating any service;
5. updates only services whose task definition differs;
6. waits for all services to become stable;
7. verifies every service is running the frozen target task definition at steady state;
8. records `database_downgrade_attempted=false`;
9. requires public `/health/ready` recovery after the rollback.

The rollback path deliberately does **not** run Alembic downgrade automatically. Database restoration follows the separate DB restore runbook only when application rollback is insufficient and the explicit RPO/data-loss trade-off is approved.

## 7. Terraform reconciliation after emergency rollback

An emergency ECS rollback changes the live ECS service to the previous task definition while the repository/Terraform configuration still describes the newer release candidate. This is intentional during incident containment.

After stability is restored:

1. freeze the rollback drill evidence;
2. keep normal production deploy automation paused;
3. decide whether the failed release is reverted in source or superseded by a fixed release;
4. run Terraform plan and verify that it will not silently roll the failed release forward again;
5. only then resume normal governed deployment.

Never run an unreviewed `terraform apply` immediately after an emergency rollback.

## 8. Required acceptance evidence

Rollback remains `VALIDATION_PENDING` until the exact release candidate has real evidence for:

- a previous known-good immutable task-definition snapshot;
- a release that actually changes at least one task definition;
- rollback to that snapshot;
- ECS steady state after rollback;
- public readiness recovery;
- no automatic database downgrade;
- incident/deployment timeline and operator identity;
- subsequent Terraform reconciliation decision.

Alerting remains `VALIDATION_PENDING` until real evidence proves:

- alert infrastructure was applied in the target AWS account;
- controlled `OK -> ALARM -> OK` transition;
- SNS -> SQS delivery for ALARM and recovery;
- production deployment failure signals reach the deployment topic;
- the approved human on-call destination receives and acknowledges a test alert.

## 9. Current blockers

At the time this source closure was authored:

- GitHub hosted Actions cannot allocate a runner because of the repository/account billing or Actions spending-limit condition;
- the root `uv.lock` remains stale relative to the workspace manifest;
- Terraform plan/apply and the AWS drills have not executed on this branch;
- human on-call destination configuration and delivery proof are external operational work.

Therefore this work may be described only as:

```text
SOURCE_IMPLEMENTED / VALIDATION_PENDING
```

It must not be converted to `PASS` until the required runtime evidence from the exact release candidate exists.
