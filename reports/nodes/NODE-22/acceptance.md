# NODE-22 Acceptance — Model Gateway

Status: **IMPLEMENTED / VALIDATING / BLOCKED_EXTERNAL**

## Implementation scope

- [x] Provider-neutral `ModelRequest` and normalized result/stream contracts.
- [x] Initial capability vocabulary for LLM/image/video/embedding/OCR.
- [x] ProviderAdapter / registry / health / budget / telemetry ports.
- [x] Capability/quality/latency/policy/region/health/budget router.
- [x] Explainable accepted/rejected routing reason codes.
- [x] Soft provider/model preferences that cannot bypass policy.
- [x] Provider-local retry separated from cross-provider fallback.
- [x] Fallback restricted to fallbackable + proven `NOT_ACCEPTED` errors.
- [x] Ambiguous accepted/unknown provider outcomes block retry/fallback.
- [x] Mandatory paid invocation guard for every ModelGateway instance.
- [x] Separate mandatory paid stream guard for streaming.
- [x] Request-local budget reservation boundary, replaceable by NODE-27.
- [x] Normalized usage, cost confidence, price snapshot, and telemetry.
- [x] Telemetry excludes raw prompts/reference assets.
- [x] Deterministic MockProvider for LLM/structured/image/video/embedding/OCR.
- [x] Mock normalized stream and async video lifecycle.
- [x] Real OpenAI Responses HTTP adapter for reasoning + structured output.
- [x] OpenAI adapter defaults to `store=false` and does not depend on SDK.
- [x] OpenAI wire contract tested through fake transport without a live key.
- [x] Provider credentials/imports statically forbidden in caller runtimes.
- [x] Provider-neutral API + client facade.
- [x] Hosted Model Gateway service accepts only signed `agent-runtime` / `worker-media` internal callers.
- [x] Agent Runtime hosted composition constructs `HttpProfileModelProvider.from_env()` and does not expose model-provider injection.
- [x] Worker Media image and video gateways construct signed private Model Gateway clients from `LUMI_MODEL_GATEWAY_URL` + `LUMI_MODEL_GATEWAY_AUTH_SECRET`.
- [x] Staging and Production IaC give Provider model/media secrets only to the `model-gateway` ECS service.
- [x] Staging and Production IaC give Agent Runtime / Worker Media only the private Model Gateway URL + internal HMAC secret for model access.
- [x] ECS execution-role and task-definition secret materialization is limited to each service's declared `secret_arns`.
- [x] Runtime-image provenance pins the Agent Runtime private model client, Worker image/video private gateway clients, and Hosted Model Gateway composition sources.
- [x] Model Gateway, Production IaC, and Final Acceptance workflows all directly execute and syntax-gate the cross-layer private deployment contract.

## Cross-layer private deployment binding

The deployment boundary is now checked as one release contract rather than as disconnected local assertions:

```text
Staging / Production IaC
  -> model-gateway owns providers/model + providers/media secrets
  -> agent-runtime gets private Model Gateway URL + internal HMAC secret
  -> worker-media gets private Model Gateway URL + internal HMAC secret
  -> ECS execution IAM can read only service-declared secret ARNs
  -> ECS task definition injects only those declared environment/secrets
  -> HostedDeepAgentRuntimeFactory -> HttpProfileModelProvider.from_env()
  -> HostedImageModelGatewayAdapter.from_env()
  -> HostedVideoGateway.from_env()
  -> signed internal Model Gateway HTTP boundary
  -> runtime-image provenance includes the exact implementation sources
```

Canonical executable source contract:

```text
scripts/validate_private_model_gateway_deployment_contract.py
```

The contract intentionally preserves the current network topology defined by the Production IaC contract. It does **not** claim Agent Runtime or Worker Media have no Internet egress; the current compute contract grants explicit Internet-egress SGs to services other than the restricted `sandbox-runtime` / `outbox-dispatcher` branch. The security claim closed here is narrower and auditable: Provider credentials are centralized in Model Gateway, Hosted Agent/Media model execution is source-bound to the signed private Gateway client, and deployment secret injection cannot give Provider model/media credentials to those callers.

## Acceptance cases authored

- [x] capability routing;
- [x] soft preference scoring;
- [x] unhealthy provider filtering;
- [x] hard budget filtering;
- [x] safe 429 fallback;
- [x] unsafe unknown 5xx outcome blocks fallback;
- [x] provider retry obeys Retry-After;
- [x] concurrent duplicate paid request -> one provider invocation;
- [x] normalized stream chunks;
- [x] async video pending/completed lifecycle;
- [x] deterministic structured MockProvider output;
- [x] provider-neutral API/client boundary;
- [x] paid guard required at construction;
- [x] OpenAI `store=false` request contract;
- [x] OpenAI standard output/usage normalization;
- [x] OpenAI structured output payload;
- [x] OpenAI 429/5xx delivery-state classification;
- [x] OpenAI key absent from adapter repr;
- [x] provider-native caller message fields rejected;
- [x] deployment Provider-secret ownership split across Staging and Production;
- [x] ECS declared-secret IAM/task injection mapping;
- [x] Agent Runtime private signed HTTP model binding;
- [x] Worker Media image private signed HTTP model binding;
- [x] Worker Media video async private signed HTTP model binding;
- [x] API/Agent/Worker/Model Gateway runtime provenance binding;
- [x] cross-layer workflow self-gating in Model Gateway / Production IaC / Final Acceptance.

## Evidence status

No hosted PASS is claimed yet. Latest sampled source-closure head: `b45c857ee9d25276bc9d826c3e18580391d78145`.

### Model Gateway

Run `32456048585`:

```text
source-contract
  job_id: 96693429449
  conclusion: failure
  steps: null
  logs_url: null

model-gateway: skipped
hosted-paid-guard-postgres: skipped
```

### Production IaC

Run `32456048507`:

```text
source-contract
  job_id: 96693429271
  conclusion: failure
  steps: null
  logs_url: null

terraform-static
  job_id: 96693429489
  conclusion: failure
  steps: null
  logs_url: null

contract-gate
  job_id: 96693458867
  conclusion: failure
  steps: null
  logs_url: null
```

### Final Acceptance

Run `32456048271`:

```text
source-contract
  job_id: 96693428258
  conclusion: failure
  steps: null
  logs_url: null

canonical-lock-gate
  job_id: 96693428476
  conclusion: failure
  steps: null
  logs_url: null

node73-final-contract-gate
  job_id: 96693468762
  conclusion: failure
  steps: null
  logs_url: null

final-decision: skipped
```

No checkout, Python compilation, private-deployment validator, Terraform validation, `uv`, Ruff, Pyright, pytest, PostgreSQL, or application command is evidenced as having run for these jobs. These failures therefore remain consistent with the existing GitHub-hosted runner/account/scheduling blocker; they are neither application-test failures nor PASS evidence.

NODE-22 remains **not COMPLETE** until the dedicated Model Gateway and release workflows actually receive runners and produce executable green evidence.

## Required green evidence

- [ ] private Model Gateway cross-layer source contract executes green;
- [ ] frozen workspace install after canonical resolver-generated `uv.lock`;
- [ ] static architecture/secret boundary;
- [ ] Ruff;
- [ ] Pyright;
- [ ] Model Gateway unit suite;
- [ ] Hosted media boundary tests;
- [ ] Deep Agents HTTP boundary tests;
- [ ] durable paid-guard PostgreSQL acceptance;
- [ ] MockProvider full integration;
- [ ] Terraform static validation for the deployment boundary;
- [ ] accepted runtime-image / Staging proof that deployed Agent Runtime and Worker Media use the private Model Gateway boundary;
- [ ] no inherited repository regression.
