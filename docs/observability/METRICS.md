# LUMI Observability Signal Contract

Status: NODE-67 baseline  
Rule: a signal is `LIVE` only after a producer, transport/export path and staging/local validation exist.

## 1. Cardinality policy

Metric labels are for bounded dimensions only. Forbidden metric dimensions include:

```text
organization_id
user_id
workspace_id
project_id
asset_id
artifact_id
run_id / agent_run_id
task_id
operation_id
request_id
provider_request_id
raw URL
prompt/output/content
```

Those values belong in privacy-safe trace attributes/log references. Route labels must use templates such as `/projects/{project_id}`.

## 2. HTTP metrics — producer implemented

### `lumi_http_requests_total`

Type: counter  
Labels: `method`, `route`, `status_class`  
Producer: `apps/api/src/lumi_api/observability`  
State: IMPLEMENTED / execution validation pending

### `lumi_http_request_duration_seconds`

Type: histogram  
Labels: `method`, `route`, `status_class`  
Buckets: 0.05, 0.1, 0.25, 0.5, 1, 2, 5 seconds  
Producer: `apps/api/src/lumi_api/observability`  
State: IMPLEMENTED / execution validation pending

`/internal/metrics` scrape requests are excluded from these two signals.

## 3. Model/provider signal projection — producer projection implemented

Source event: `TelemetryEvent` in Model Gateway.  
Projection: `services/model-gateway/src/lumi_model_gateway/telemetry.py`.

Bounded metric dimensions:

```text
provider
outcome = success | error
```

Trace attributes may contain:

```text
lumi.request_id
lumi.operation_id
lumi.organization_id
lumi.project_id
lumi.task_id
lumi.agent_run_id
lumi.generation_id
lumi.trace_id
lumi.capability
gen_ai.system
gen_ai.request.model
gen_ai.response.id
lumi.attempt
lumi.fallback_index
lumi.retry_count
error.type
```

No prompt, model output, signed URL or auth credential is part of the projection.

Planned exported metrics after explicit OTel SDK/exporter dependency and lockfile integration:

```text
lumi_model_requests_total{provider,outcome}
lumi_model_request_duration_seconds{provider,outcome}
lumi_model_cost_usd_total{provider,outcome}
lumi_model_retry_total{provider,outcome}
lumi_model_fallback_total{provider,outcome}
```

State: PROJECTION IMPLEMENTED / OTEL EXPORTER NOT YET WIRED.

The Cost Ledger remains authoritative for financial reporting; observability cost counters are operational trend signals only.

## 4. Agent runtime signals

Correlation refs contract:

```text
agent_run_id
organization_id
project_id
task_id
operation_id
trace_id
```

LangSmith policy defaults to no tracing and hides inputs/outputs when tracing is enabled. Telemetry callbacks are best effort.

Target metrics:

```text
lumi_agent_runs_total{outcome}
lumi_agent_run_duration_seconds{outcome}
lumi_agent_task_total{outcome}
lumi_agent_approval_wait_seconds{outcome}
lumi_agent_graph_depth{outcome}
```

State: CORRELATION/PRIVACY POLICY IMPLEMENTED; metric producer integration pending.

## 5. Queue/worker signals

Event contract already carries:

```text
id
correlationid
causationid
traceid
organizationid
```

Worker correlation helper exists in `apps/worker-media/src/lumi_worker_media/observability.py` and the consumer binds/resets it around handler execution.

Target metrics:

```text
lumi_queue_published_total{event_type,outcome}
lumi_queue_consumed_total{event_type,outcome}
lumi_queue_processing_duration_seconds{event_type,outcome}
lumi_queue_dlq_total{event_type,reason}
lumi_queue_lag_seconds{event_type}
```

High-cardinality message/event IDs remain trace/log refs.

State: CORRELATION PATH IMPLEMENTED / QUEUE METRIC EXPORTERS PENDING.

## 6. Quality signals

Canonical source: Visual Critic / Auto Repair / benchmark/eval engines.

Target metrics:

```text
lumi_quality_score{service,outcome}
lumi_quality_gate_total{outcome,reason}
lumi_auto_repair_total{outcome,reason}
lumi_eval_regression_total{outcome,reason}
```

State: NOT YET CONNECTED TO NODE-67 EXPORT PATH.

## 7. Cost/budget signals

Canonical source: Cost Ledger / Billing entitlements.

Target operational metrics:

```text
lumi_budget_guard_total{outcome,reason}
lumi_cost_reconciliation_total{outcome,reason}
```

Never export tenant billing balances as high-cardinality Prometheus labels. Per-tenant financial questions remain database/ledger queries with authorization.

State: NOT YET CONNECTED TO NODE-67 EXPORT PATH.

## 8. Security/audit signals

Canonical source: NODE-65 Audit/Governance and NODE-66 security controls.

Target aggregate metrics:

```text
lumi_auth_failures_total{reason}
lumi_authorization_denied_total{reason}
lumi_security_policy_block_total{reason}
lumi_sandbox_violation_total{reason}
```

Do not expose user identity, tenant identity, secret values, prompt content or raw policy payloads as metric labels.

State: NOT YET CONNECTED TO NODE-67 EXPORT PATH.

## 9. Collector/backend signals

Local stack:

```text
OpenTelemetry Collector internal metrics :8888
OTel Prometheus exporter :9464
Prometheus
Tempo
Loki
Grafana
```

Collector redaction removes known credential/content attributes before backend export. Local debug exporter is a troubleshooting aid only; production Collector configuration must not rely on debug output and requires environment-specific TLS/auth/storage/retention.

## 10. Dashboard truthfulness policy

A dashboard panel may be provisioned before its producer only if it is explicitly marked as pending/no-data and is not used as acceptance evidence. NODE-67 acceptance requires producer + transport + backend query + dashboard/alert validation for each claimed LIVE domain.

## 11. Browser/frontend signals — source producer implemented

Canonical source:

```text
apps/web/src/lib/observability/browser.ts
apps/web/src/components/BrowserObservability.tsx
apps/web/src/app/api/telemetry/browser/route.ts
```

Bounded event kinds:

```text
route_error
runtime_error
canvas_error
api_failure
web_vital
```

Bounded Web Vital names:

```text
ttfb_ms
lcp_ms
cls
inp_ms
```

Browser telemetry may include only normalized route template/path, bounded numeric value, HTTP status class, safe request/correlation IDs and fixed/bounded error codes. It must not include error message/stack, query strings, prompt/output, Canvas content/screenshot, request/response body, Authorization/Cookie, signed URL or user file contents.

Sampling baseline:

```text
errors/API failures: 100%
Web Vitals/performance: 10%
```

The same-origin Next.js intake re-sanitizes events, caps request bytes and rejects cross-site submissions before emitting structured server logs. `observedFetch` can project `X-Request-ID` / `X-Correlation-ID` from failed API responses into the browser error record without copying response bodies.

State: SOURCE PRODUCER + SAME-ORIGIN INTAKE IMPLEMENTED / EXECUTION VALIDATION AND BACKEND AGGREGATION PENDING.

A future Prometheus/OTel browser aggregate must use only bounded labels such as event kind, Web Vital name, route template and status class. Request/correlation IDs remain trace/log references and must never become metric labels.
