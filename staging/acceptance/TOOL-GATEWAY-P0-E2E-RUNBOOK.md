# Tool Gateway P0 — Production-like Staging E2E Runbook

Status: **release-blocking evidence procedure** for NODE-73.

This runbook does not grant PASS by itself. It defines the synthetic, exact-RC evidence chain consumed by the Tool Gateway E2E validator and Staging Acceptance.

## 1. Release identity is non-negotiable

Collect only against a frozen Production-like Staging release candidate.

The evidence chain must bind:

- full 40-character Git SHA;
- digest-pinned API image;
- digest-pinned Agent Runtime image;
- digest-pinned Tool Gateway image;
- digest-pinned Sandbox Runtime image;
- the canonical parent `container_image_set` used by Staging Acceptance.

Mutable tags are not evidence.

`scripts/run_tool_gateway_p0_staging_e2e_ecs.py` records the **actually deployed** task-definition images. It does not claim that those images are the RC merely because the caller supplied an RC SHA. `scripts/validate_tool_gateway_p0_runtime_identity.py` must later join the runtime identity to the canonical parent staging evidence and require exact SHA/image equality.

## 2. Synthetic-only fixture

Production customer data is forbidden.

The canonical fixture materializer is:

```text
python -m lumi_api.tool_gateway_staging_fixture
```

It runs as a one-shot task derived from the deployed API service and reuses the canonical synthetic seed organization/project. It deterministically materializes and collision-checks:

- one AgentRun;
- one Task bound to the AgentRun/project;
- one ready source Asset;
- complete source AssetRights allowing derived creation;
- one Artifact in the same project.

The materializer uses a PostgreSQL advisory lock and fails closed if a deterministic fixture ID already exists with different identity-bearing fields.

Fixture resource IDs are stable. **NODE-20 idempotency keys are not stable.** Every evidence collection creates a fresh run-scoped idempotency key so the run can independently prove first execution plus replay without reusing a previous acceptance operation.

## 3. One canonical staging launcher

Use:

```text
scripts/run_tool_gateway_p0_staging_e2e_ecs.py
```

The launcher discovers the deployed ECS services directly from `lumi-staging-cluster`:

1. `api`
2. `agent-runtime`
3. `tool-gateway`
4. `sandbox-runtime`

For each service it reuses the deployed service's exact task definition and `awsvpc` network configuration. It requires:

- active ECS service;
- digest-pinned deployed image;
- private subnets;
- declared security groups;
- `assignPublicIp=DISABLED`;
- canonical `awslogs` configuration.

It does not retrieve Secrets Manager values and does not pass product secrets through ECS overrides. The one-shot API and Agent Runtime tasks inherit the same task-definition secret bindings as their deployed services.

Execution order:

1. API one-shot materializes the synthetic fixture.
2. Launcher reads only the sanitized fixture marker from API CloudWatch logs.
3. Launcher creates a fresh run-scoped NODE-20 key and trace prefix.
4. Agent Runtime one-shot executes the P0 probe.
5. The same Agent Runtime one-shot independently collects PostgreSQL audit/idempotency/rights evidence and Tool Gateway readiness.
6. The launcher records the four deployed runtime identities and sanitized ECS task metadata.

GitHub itself does not query the staging application database and does not receive internal HMAC secrets.

## 4. Probe semantics: 8 P0 tools + 2 independent follow-up calls

The raw Agent Runtime probe is:

```text
scripts/probe_tool_gateway_p0_from_agent_runtime.py
```

The first eight calls are exactly:

1. `web.search@1.0.0`
2. `web.fetch@1.0.0`
3. `project.query@1.0.0`
4. `asset.read@1.0.0`
5. `artifact.query@1.0.0`
6. `media.inspect@1.0.0`
7. `asset.write-derived@1.0.0`
8. `sandbox.execute@1.0.0` — normal small-output execution

The probe then makes two additional calls with distinct `tool_call_id` values:

9. `asset.write-derived@1.0.0` replay using the same idempotency key and equivalent arguments;
10. a **separate** oversized `sandbox.execute@1.0.0` call dedicated to result-offload proof.

Therefore the durable audit evidence requires **10 distinct tool-call IDs**. The normal sandbox call proves execution semantics; the oversized sandbox call proves result-offload semantics. They must never be collapsed into one call.

## 5. Real oversized-result semantics

Tool Gateway intentionally does **not** replace an oversized result with `data=null`.

For an oversized output, the real runtime does all of the following:

- serializes the complete canonical result;
- stores the complete result in the private exports bucket;
- returns `full_result_ref=s3ref://...#sha256=...`;
- returns `truncated=true`;
- keeps a **bounded inline preview** in `ToolResult.data` so the Agent retains limited context without receiving the full payload.

The raw probe therefore legitimately reports:

```text
inline_data_present = true
truncated = true
full_result_ref = s3ref://...
```

`scripts/validate_tool_gateway_p0_offload_probe.py` validates the real semantics and requires:

```text
inline_preview_present = true
inline_preview_bytes <= 64 KiB
full_payload_inline_present = false
serialized S3 result bytes > 64 KiB
```

The legacy v1 final evidence field `inline_data_present=false` is retained only as a compatibility meaning of **"the complete payload is not inline"**. `scripts/assemble_tool_gateway_p0_e2e_evidence_v2.py` first validates the untouched raw probe, then creates a compatibility view for the legacy assembler and emits explicit v2 fields:

```text
semantics_version = 2
truncated = true
inline_preview_present = true
inline_preview_bytes = <measured>
full_payload_inline_present = false
```

Do not alter the raw probe to hide the preview.

## 6. Independently prove readiness

`scripts/collect_tool_gateway_p0_readiness.py` calls the exact private deployed Tool Gateway `/health/ready` endpoint from the Agent Runtime trust boundary.

Required values:

```json
{
  "service": "tool-gateway",
  "status": "ok",
  "adapter_count": 8,
  "runtime_binding_count": 4,
  "missing_adapters": [],
  "missing_runtime_bindings": []
}
```

A health-only process with missing production adapters cannot pass.

## 7. Independently prove NODE-20 replay and durable state

`scripts/collect_tool_gateway_p0_db_evidence.py` reads the canonical PostgreSQL state from inside the staging application trust boundary.

It must prove:

- all 10 expected tool calls have durable audit events;
- the first write and replay resolve through canonical NODE-20 state;
- replay returns the same derived `asset://<uuid>`;
- the adapter was invoked once;
- exactly one derived Asset exists;
- no duplicate derived Asset exists;
- derived rights exactly inherit the source rights fields;
- no cross-tenant audit rows are admitted;
- secret material is absent from persisted evidence.

Required replay invariants include:

```text
adapter_invocation_count = 1
duplicate_derived_asset_count = 0
replayed = true
first_asset_ref == replay_asset_ref
```

## 8. Independently prove private S3 offload

`scripts/verify_tool_gateway_p0_offload_s3.py` runs under the release-evidence AWS role, not under Agent Runtime.

It parses the exact `s3ref://...#sha256=...` from the raw offload call and uses S3 metadata/control-plane APIs only. It proves:

- the object exists in the canonical staging exports bucket;
- object length exceeds the 64 KiB inline threshold;
- SHA-256 metadata agrees with the result ref;
- content type is `application/json`;
- KMS encryption is enabled;
- PublicAccessBlock is fully enabled;
- ownership is `BucketOwnerEnforced`;
- bucket policy status is non-public;
- lifecycle expiration is enabled;
- no public or presigned URL is returned.

The evidence collector must not download the offloaded payload just to prove it exists.

## 9. Live Brave search evidence

A unit test is not live provider evidence.

`scripts/derive_tool_gateway_p0_search_evidence.py` joins:

- the successful exact-RC `web.search` probe result;
- the digest-pinned Tool Gateway image from parent staging evidence;
- required Tool Gateway source provenance for the fixed Brave backend and no-redirect transport.

The final evidence requires:

```text
provider = brave
provider_host = api.search.brave.com
provider_http_status = 200
result_count > 0
redirect_followed = false
credential_material_present = false
```

Never store `LUMI_BRAVE_SEARCH_API_KEY` or `X-Subscription-Token` in evidence.

## 10. Scoped reads must not expose storage internals

For `asset.read`, `artifact.query`, and `media.inspect`, the assembled evidence must prove:

```text
storage_location_exposed = false
```

Responses must not disclose raw bucket names, object keys, provider credentials, or presigned URLs. Canonical internal refs such as `asset://...` and `artifact://...` are allowed.

## 11. Collection workflow: evidence only, never PASS

Run the workflow:

```text
Collect Staging Tool Gateway P0 E2E
```

It is `workflow_dispatch`-only and requires:

```text
release_git_sha = <exact 40-char RC SHA>
collect_ack = COLLECT_TOOL_GATEWAY_P0
```

It performs:

- exact checkout SHA assertion;
- AWS OIDC staging role assumption;
- synthetic API fixture one-shot;
- Agent Runtime probe + DB + readiness one-shot;
- independent S3 offload verification;
- raw preview/offload semantic validation;
- evidence checksums.

Its status file is deliberately:

```text
COLLECTED_NOT_ACCEPTED
```

A successful collector run is **not** Staging PASS because it has not yet proved that the deployed runtime digests equal the canonical parent RC image set.

## 12. Freeze/assemble workflow: exact-RC join

Run the workflow:

```text
Freeze Staging Tool Gateway P0 E2E
```

It requires:

- exact RC SHA;
- successful collector workflow run ID;
- canonical parent staging evidence path below `reports/staging-acceptance/`;
- acknowledgement `FREEZE_STAGING_TOOL_GATEWAY_P0:<rc-sha>`.

The freezer revalidates the source workflow identity and exact `head_sha`, downloads exactly one copy of each independent evidence file, and then requires:

1. raw offload semantics pass again;
2. runtime SHA equals parent staging RC SHA;
3. deployed API digest equals parent API digest;
4. deployed Agent Runtime digest equals parent Agent Runtime digest;
5. deployed Tool Gateway digest equals parent Tool Gateway digest;
6. deployed Sandbox Runtime digest equals parent Sandbox Runtime digest;
7. all four services used private deployed network identities;
8. Brave evidence derives from the exact-RC probe plus canonical provenance;
9. v2 Tool Gateway evidence assembly passes the legacy contract plus explicit preview semantics.

The immutable package is frozen under:

```text
reports/staging-acceptance/<rc-sha>/tool-gateway-p0-e2e/
```

An existing non-identical package for the same RC SHA is never overwritten.

## 13. Final validation and Staging Acceptance

The standalone Tool Gateway evidence is still validated by:

```bash
python3 scripts/validate_tool_gateway_e2e_evidence.py \
  --evidence reports/staging-acceptance/<rc-sha>/tool-gateway-p0-e2e/tool-gateway-e2e.json
```

The freeze package also contains a merged staging evidence candidate with the Tool Gateway object embedded at:

```text
tool_gateway_e2e
```

That merged file must then pass the normal Staging Acceptance decision chain. Tool Gateway P0 evidence does not waive:

- canonical frozen dependency graph;
- six-image build/SBOM/provenance gates;
- PostgreSQL migrations and ORM drift checks;
- Terraform plan/apply and live network probes;
- media-generation E2E;
- rollback/DR/security/performance/AI regression gates;
- production smoke/canary evidence.

## Release rule

Keep NODE-73 **BLOCKED** if any of these is missing:

- exact RC runtime identity join;
- synthetic-only fixture proof;
- 8/8 readiness;
- all 8 P0 first calls;
- independent write replay call;
- independent oversized sandbox offload call;
- 10/10 durable audit events;
- live Brave search evidence;
- inherited rights;
- private S3 `HeadObject`/bucket-control evidence;
- bounded preview + durable full-result proof;
- immutable frozen evidence package;
- full Staging Acceptance PASS.
