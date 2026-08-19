# Tool Gateway P0 — Production-like Staging E2E Runbook

Status: **release-blocking evidence procedure** for NODE-73.

This runbook does not grant PASS by itself. It defines how to collect the independent evidence consumed by `scripts/validate_tool_gateway_e2e_evidence.py`.

## 1. Non-negotiable release identity

Run the probe only after the staging release candidate is frozen.

Capture before any tool call:

- full 40-character Git SHA;
- release version returned by the deployed control plane;
- digest-pinned API image;
- digest-pinned Agent Runtime image;
- digest-pinned Tool Gateway image;
- the same `container_image_set_ref` used by Staging Acceptance.

Do not accept mutable tags such as `latest`, branch names, or semver tags without an image digest.

The final Tool Gateway E2E evidence must bind these identities to the parent staging evidence. The validator rejects evidence from another SHA, version, API image, Agent Runtime image, or Tool Gateway image.

## 2. Data and identity boundary

Use synthetic staging data only. Production customer data is forbidden.

Prepare or select one synthetic organization/project containing:

- one ready source Asset with an AssetRights row;
- one Artifact in the same project;
- one AgentRun in the same organization/project;
- one Task bound to that AgentRun/project.

The Task is the canonical project-scope anchor. Tool arguments must not be allowed to choose another `project_id`.

Never place raw secret values in evidence. Record only secret resource identity or redacted deployment metadata when needed.

## 3. Run the Agent Runtime P0 probe

The probe is `scripts/probe_tool_gateway_p0_from_agent_runtime.py`.

Run it **inside the deployed Agent Runtime execution identity**, for example as a one-off task based on the exact accepted Agent Runtime task definition/image. Do not run it from a developer laptop and do not inject the Tool Gateway secret into an unrelated runtime.

Required environment:

```text
LUMI_TOOL_GATEWAY_URL
LUMI_TOOL_GATEWAY_AUTH_SECRET
LUMI_PROBE_ORGANIZATION_ID
LUMI_PROBE_AGENT_RUN_ID
LUMI_PROBE_TASK_ID
LUMI_PROBE_SOURCE_ASSET_ID
LUMI_PROBE_ARTIFACT_ID
LUMI_PROBE_DERIVED_IDEMPOTENCY_KEY
```

Optional environment:

```text
LUMI_PROBE_SEARCH_QUERY
LUMI_PROBE_FETCH_URL
LUMI_PROBE_TRACE_PREFIX
LUMI_PROBE_OUTPUT
```

The probe invokes exactly these P0 tools:

1. `web.search@1.0.0`
2. `web.fetch@1.0.0`
3. `project.query@1.0.0`
4. `asset.read@1.0.0`
5. `artifact.query@1.0.0`
6. `media.inspect@1.0.0`
7. `asset.write-derived@1.0.0`
8. `sandbox.execute@1.0.0`

It then repeats `asset.write-derived` with the same idempotency key and equivalent arguments.

The sandbox probe intentionally emits more than the P0 inline result limit so the Tool Gateway result-offloader must return an internal `s3ref://...#sha256=...` rather than inline data.

The probe output is **raw call evidence**, not the final PASS artifact.

## 4. Independently prove readiness

Capture `/health/ready` from the exact Tool Gateway RC before the probe.

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

Store the unmodified response in the release evidence bundle and reference it from `readiness.probe_ref`.

## 5. Independently prove NODE-20 replay

Do not rely only on the second HTTP response saying `replayed=true`.

From PostgreSQL, collect the canonical side-effect operation for the write tool and prove:

- the first and replay call resolve to the same operation identity/idempotency key hash;
- the adapter was invoked once;
- replay returned the same `asset://<uuid>`;
- exactly one derived Asset exists for the accepted operation;
- no duplicate derived Asset was materialized.

The final evidence requires:

```text
adapter_invocation_count = 1
duplicate_derived_asset_count = 0
replayed = true
first_asset_ref == replay_asset_ref
```

## 6. Independently prove derived Asset rights

Read the source AssetRights and derived AssetRights rows from PostgreSQL.

The derived Asset must inherit the canonical rights fields from the source Asset. The source Asset and Artifact must both belong to the Task project.

Record `rights_inherited=true` only after comparing the persisted rows. Do not infer it from request metadata.

## 7. Independently prove durable audit

Query the canonical durable Tool audit store by the probe tool-call IDs/trace IDs.

Required evidence:

- every first-call P0 tool has a persisted audit row;
- the replay call is represented according to the canonical audit contract;
- no expected tool-call ID is missing;
- no cross-tenant audit row is returned for the probe scope;
- raw provider/API/internal secrets are absent from persisted audit material.

The final evidence must report an exact expected/persisted count and an empty `missing_tool_calls` array.

## 8. Independently prove S3 offload

Take the `s3ref://...#sha256=...` returned by the oversized sandbox result and parse the private bucket/key/hash.

Using an authorized release-evidence role, perform `HeadObject` against that exact object and prove:

- object exists in the accepted exports bucket;
- object length exceeds the tool inline threshold;
- SHA-256 metadata/checksum agrees with the result ref;
- the object is not represented by a public or presigned URL in the tool result;
- the object is covered by the staging KMS/PublicAccessBlock/TLS-only storage boundary.

The Agent Runtime probe itself should not be granted extra exports-bucket permission just to make this check convenient. Keep the object-store check independent.

## 9. Independently prove live Brave search

A successful parser/unit test is not live provider evidence.

For the `web.search` call, prove from the deployed request/result and release logs/metrics that:

- provider is Brave;
- provider host is `api.search.brave.com`;
- an actual provider request occurred during the probe window;
- provider returned HTTP 200;
- at least one normalized search result was returned;
- no redirect was followed;
- provider credential material is absent from evidence/log output.

Never store `LUMI_BRAVE_SEARCH_API_KEY` or `X-Subscription-Token` in evidence.

## 10. Prove scoped reads do not disclose storage location

For `asset.read`, `artifact.query`, and `media.inspect`, inspect the returned JSON and record:

```text
storage_location_exposed = false
```

The response must not expose raw S3 bucket names, object keys, provider credentials, or presigned URLs. Resource identity should be represented through canonical internal refs such as `asset://...` and `artifact://...`.

## 11. Assemble the final Tool Gateway E2E object

Use `staging/acceptance/tool-gateway-e2e-v1.json` as the schema/template, replacing every `PENDING` value with measured evidence.

The final object may be stored standalone for review, but Staging Acceptance must embed the complete object at:

```text
tool_gateway_e2e
```

inside the full staging evidence JSON.

Do not paste the template placeholder into a release evidence file and call it complete. The validator recursively rejects any remaining `PENDING` value.

## 12. Validate before release decision

Standalone validation:

```bash
python3 scripts/validate_tool_gateway_e2e_evidence.py \
  --evidence reports/staging-acceptance/runtime/tool-gateway-e2e.json
```

Full Staging Acceptance validation must use the full staging evidence file. This additionally proves the Tool Gateway E2E SHA/version/API/Agent Runtime/Tool Gateway images exactly match the parent RC evidence.

A structural PASS does not waive the normal Staging Acceptance, frozen dependency graph, image provenance, migration, security, rollback, DR, or production-readiness gates.

## Release rule

If any of the following is missing, NODE-73 stays BLOCKED:

- frozen dependency graph;
- exact RC identities;
- 8/8 Tool Gateway readiness;
- all 8 P0 calls;
- live Brave search;
- same-result NODE-20 replay;
- inherited rights;
- durable audit;
- private S3 offload HEAD verification;
- exact evidence-to-RC identity binding.
