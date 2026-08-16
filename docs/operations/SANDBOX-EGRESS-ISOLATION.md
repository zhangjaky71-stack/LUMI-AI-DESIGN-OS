# Sandbox Egress Isolation — Production Runbook

> Final Acceptance control: sandbox code execution must not have arbitrary Internet or business-database reachability.

## Source boundary

Production and staging use two independent controls:

1. `sandbox-runtime` is scheduled into the **data/isolated subnets**, whose route tables intentionally have no `0.0.0.0/0` route to NAT or an Internet Gateway.
2. `sandbox-runtime` receives a dedicated sandbox security group rather than the ordinary application security group.

The sandbox security group permits VPC-local traffic and HTTPS to the S3 managed prefix list only. Required AWS control-plane/data-plane dependencies are private:

- ECR API interface endpoint;
- ECR Docker interface endpoint;
- CloudWatch Logs interface endpoint;
- Secrets Manager interface endpoint;
- KMS interface endpoint;
- S3 gateway endpoint.

Redis and RabbitMQ explicitly trust the sandbox security group. PostgreSQL deliberately does **not** trust it.

## Deployment invariants

The release candidate is invalid if any of these become false:

```text
sandbox-runtime.isolated_network == true
sandbox ECS subnet set == core.data_subnet_ids
sandbox ECS security group == core.sandbox_security_group_id
data route tables have no 0.0.0.0/0 route
sandbox security group has no 0.0.0.0/0 egress
PostgreSQL SG does not trust sandbox SG
Redis/RabbitMQ SGs may trust sandbox SG
sandbox task has assign_public_ip == false
```

Static source contract:

```bash
python scripts/validate_final_hard_stops.py
terraform fmt -check -recursive infra/iac
```

Static validation is necessary but is not production evidence.

## Required staging probe

Run against the exact staging release candidate after Terraform apply. Execute the probe **inside a sandbox-runtime task or a one-off task using the exact same subnets, security group, execution role and task role**.

Expected PASS matrix:

| Probe | Expected |
|---|---|
| DNS for internal service discovery | PASS |
| TLS connection to configured Redis | PASS |
| TLS/AMQPS connection to configured RabbitMQ | PASS |
| read/write only the declared sandbox S3 bucket | PASS |
| CloudWatch Logs delivery | PASS |
| declared Secrets Manager secret retrieval by execution role | PASS |
| HTTPS to arbitrary public site | **FAIL** |
| TCP to public IP:443 | **FAIL** |
| TCP to PostgreSQL endpoint:5432 | **FAIL** |
| access to non-declared S3 bucket | **FAIL** |

Do not loosen the sandbox SG or add a NAT route merely to make a probe pass. A required AWS dependency must be satisfied with an explicit private endpoint or a narrowly scoped internal dependency.

## Evidence package

Archive the following for NODE-73:

```text
release SHA
terraform plan artifact
terraform apply result
sandbox ECS service/task network configuration
isolated route table dump
sandbox SG ingress/egress dump
AWS VPC endpoint list and status
positive internal dependency probes
negative arbitrary Internet probe
negative PostgreSQL probe
negative undeclared S3 probe
CloudWatch log delivery proof
timestamp and AWS account/region identity
```

Credentials, secret values and customer data must be redacted. Resource IDs and account identifiers may be redacted in externally shared copies, but the internal evidence package must retain enough identifiers to prove the tested resources belong to the release environment.

## Failure semantics

If arbitrary Internet or PostgreSQL access succeeds from the sandbox network identity, Final Acceptance is **FAIL**. Do not downgrade this to a warning.

If private ECR/Logs/Secrets/KMS/S3 access fails while public Internet remains blocked, the isolation boundary is still doing its job, but the deployment is operationally incomplete and cannot be accepted until the missing private dependency is repaired.
