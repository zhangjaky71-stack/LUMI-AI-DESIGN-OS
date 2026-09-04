# Local Alibaba Cloud deployment record

Updated: 2026-09-04

## Decision

LUMI staging is being migrated from the AWS reference topology to Alibaba Cloud. The working branch is `codex/alicloud-deployment`; the original `release-closure-p0` branch is unchanged.

The deployment region is `cn-hangzhou`. The service-compatible zone set is `cn-hangzhou-h`, `cn-hangzhou-i`, `cn-hangzhou-j`.

## Authentication

Alibaba Cloud CLI OAuth profile `lumi-deploy` is valid for account `1153410507483251`. OAuth tokens and AccessKey material are local credentials and must never be printed, copied into Terraform variables, or committed.

## Verified facts

- Terraform `1.14.6`, Alibaba Cloud Provider `1.291.0`, and Random Provider `3.9.0` are pinned.
- Bootstrap configuration validates successfully.
- The Hangzhou bootstrap created the state bucket, ACL, versioning, AES256 encryption, public-access block, and TableStore instance.
- TableStore instance `lumi-tf-3251` and table `terraform_lock` are live, imported and covered by a zero-change Bootstrap plan.
- Core uses the private OSS backend with TableStore locking. Terraform requests on this host use process-only `GODEBUG=http2client=0` because the local tunnel resets HTTP/2 TableStore traffic.
- The current real Core plan contains 67 creates and zero updates/deletes. It includes ACK Managed Pro Auto Mode, three NAT gateways/EIPs, RDS, Redis, OSS protections, ACR, SLS and separate application/migration database accounts; it has not been applied.
- Hangzhou exposes the required VSwitch zones and PostgreSQL 15/Redis SKU candidates.
- The repository has six runnable Dockerfile boundaries: API, Agent Runtime, Model Gateway, Tool Gateway, Worker Media, and Sandbox Runtime.
- RabbitMQ is required by the actual application contracts. Celery and Kombu use the `lumi.jobs`, `lumi.domain`, and `lumi.dlx` exchanges, four job queues, and four dead-letter queues.
- ACK Managed Pro Auto Mode is now the selected compute target, with private control-plane exposure, RRSA, Terway, ALB ingress, ACR credential helper, logging, metrics and DNS add-ons.
- OSS compatibility is implemented with the internal Hangzhou S3 endpoint, virtual-host addressing and Signature V2; AWS remains Signature V4 by default.
- The Sandbox Runtime can now launch short-lived ACK Jobs through an in-cluster, Job-only API client while retaining ECS as a rollback backend.
- ACK manifests cover seven persistent workloads, five private services, health probes, rolling updates, ALB ingress, Sandbox RBAC/network boundaries and an Alembic migration Job.

## Current plan

Bootstrap creates:

- `lumi-terraform-state-1153410507483251-cn-hangzhou`
- TableStore instance `lumi-tf-3251`
- TableStore table `terraform_lock`

Core creates:

- VPC `10.42.0.0/16`
- public, app and data VSwitches in all three selected zones
- one pay-as-you-go NAT/EIP per app zone
- private/versioned/encrypted OSS buckets for assets, exports and sandbox exchange
- RDS PostgreSQL 15 using `pg.n1e.1c.1m`, `cloud_essd`, 20 GB
- Redis `redis.amber.master.small.multithread` across zones `i/j`
- six private ACR repositories
- SLS project and six logstores
- optional Message Queue for RabbitMQ topology, disabled until activation and cost approval
- generated RDS/Redis credentials stored only as sensitive values in encrypted Terraform state
- separate `lumi_app` and `lumi_migration` RDS accounts, with ReadWrite and DBOwner database grants respectively
- ACK Managed Pro cluster in Auto Mode

## Continue after source review and cost approval

1. Complete local lint, unit, YAML, Terraform and contract validation.
2. Regenerate the real Core plan with ACK and the migration account, then review regions, zones, SKUs, exposure and recurring cost.
3. Apply Core only after explicit recurring-cost approval.
4. Configure the GitHub ACR credentials, push the branch and run the hosted six-image build on the exact release commit.
5. Bind verified Terraform outputs, six immutable image digests, TLS domain/certificate and protected Secret values into the ACK templates.
6. Run the one-shot Alembic Job and require exit code 0 plus head `0023_video_generation_runtime`.
7. Apply all seven workloads and wait for successful rollouts.
8. Run health, queue, database, object-storage, Sandbox Job and end-to-end smoke checks.

Do not call this migration complete before steps 1-9 have cloud evidence.
