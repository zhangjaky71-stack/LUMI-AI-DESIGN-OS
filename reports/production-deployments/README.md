# Production Deployment Evidence Archive

NODE-72 production deployments are evidence-backed records, not a mutable "latest" folder.

## Layout

For every attempted production deployment, create:

```text
reports/production-deployments/<deployment-id>/
  manifest.json
  deployment-gate.json
  secrets-ready.json
  predeploy-snapshot.json
  migration.json
  ecs-deployment-state.json
  production-smoke.json
  rollback-drill.json            # when exercised
  notes.md
```

The committed `manifest.json` is the intent/approval record. Runtime JSON files are produced by controlled deployment automation and should be copied from the GitHub Actions artifact into the durable release record after review.

## Immutable identity

A record must preserve:

```text
deployment_id
exact Git SHA
release version
migration head
NODE-71 decision_id
six @sha256 image identities
previous deployment/manifest
AWS account + region
production domain
```

Never overwrite one deployment directory with a later attempt. Use a new deployment ID.

## PASS meaning

A deployment is not PASS because Terraform applied. A production deployment evidence set is complete only when all required controls for that release have succeeded, including:

- exact NODE-71 acceptance binding;
- Secret readiness;
- pre-deploy DB snapshot;
- migration exit 0;
- ECS canary/rolling steady state;
- production read-only smoke;
- required approvals and incident-free observation;
- rollback path evidence required by release policy.

Missing external/cloud evidence remains missing; do not synthesize `PASS` files.
