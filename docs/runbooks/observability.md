# LUMI Observability Runbook

Status: NODE-67 baseline  
Audience: Platform / SRE / API / Agent owners

## 1. Fast triage

Start with the user-visible symptom, then pivot by the correlation identifiers returned in API response headers or stored on the run/event:

```text
X-Request-ID
X-Correlation-ID
traceparent -> trace_id
agent_run_id / task_id / operation_id
provider_request_id when available
```

Never ask operators to paste API keys, cookies, prompts, signed URLs, uploaded document contents or model outputs into tickets. Use IDs and redacted metadata.

Local development:

```bash
make observability-up
make observability-smoke
make observability-status
make observability-logs
```

Grafana local default: `http://127.0.0.1:3001`. The local admin password defaults only for local development and must not be used in shared/staging/production environments.

## 2. API SLO breach

Trigger examples: `LumiApiHighErrorRate`, user reports of repeated 5xx, or fast error-budget burn.

1. Open Grafana `LUMI Operational Overview`.
2. Identify affected normalized routes and status class; do not pivot on raw URLs or tenant IDs in Prometheus.
3. Use a representative `trace_id` in Tempo to locate slow/failing spans.
4. Pivot from trace to Loki using the same trace ID and inspect redacted structured events.
5. Check provider/queue dependencies only if the trace crosses those boundaries.
6. If impact started after a deploy, compare deployment/release markers and rollback when safer than forward-fixing.
7. If cross-tenant exposure, repeated paid side effects or usable secret exposure is suspected, invoke NODE-66 STOP SHIP/incident procedure immediately.

Resolution evidence: incident timeline, affected SLI, root cause, rollback/fix reference, post-fix query showing recovery, and a regression test or detector where practical.

## 3. API latency

Trigger: `LumiApiP95LatencyHigh` or a sustained user-visible latency regression.

Check in order:

1. Route-template P95/P99 and request volume.
2. Database spans/query durations and pool saturation when DB instrumentation is enabled.
3. Queue acceptance versus completion latency for async routes.
4. Tool/model spans for calls that should not be on the synchronous acceptance path.
5. CPU/memory/runtime saturation and autoscaling signals once NODE-69 capacity metrics are active.

Do not increase the SLO threshold to make the alert disappear. If the product contract legitimately changes, version the SLO and document the decision.

## 4. Telemetry pipeline

Trigger: `LumiOtelCollectorDown`, missing Prometheus target, missing traces/logs, or exporter errors.

Local checks:

```bash
make observability-smoke
curl -fsS http://127.0.0.1:13133/
curl -fsS http://127.0.0.1:9090/-/ready
curl -fsS http://127.0.0.1:3200/ready
curl -fsS http://127.0.0.1:3100/ready
```

Then inspect Collector logs and its internal metrics. Validate receiver/exporter queue failures, rejected telemetry, memory limiter pressure and backend readiness.

**Business-path invariant:** do not make API/Agent/Provider execution depend on telemetry availability. Application instrumentation is best effort; telemetry failure may remove evidence but must not transform a successful business operation into a failed one.

If telemetry is unavailable during a release decision, the release remains unproven where the acceptance criterion requires telemetry evidence.

## 5. LangSmith outage or privacy issue

LangSmith is an AI/Agent trace backend, not the sole infrastructure observability path.

- Default `LANGSMITH_TRACING=false` unless a deployment enables it.
- Default `LANGSMITH_HIDE_INPUTS=true` and `LANGSMITH_HIDE_OUTPUTS=true`.
- Production must reject enabled tracing that exposes inputs or outputs without an explicit privacy review/change to the policy implementation.
- API keys/endpoints come from the deployment secret manager and are never synthesized into source-controlled environment maps.

If LangSmith is unavailable, Agent execution continues. Use OTel/Tempo/Loki and durable run/task records for diagnosis. If potentially sensitive content was captured, disable tracing, preserve access/audit evidence, follow data-retention/deletion policy, and invoke security/privacy incident handling.

## 6. Trace/log correlation

HTTP middleware accepts valid W3C `traceparent`, generates safe request/correlation IDs when incoming values are invalid, and returns correlation headers.

Use normalized identifiers:

```text
HTTP request -> request_id / correlation_id / trace_id
Agent run -> agent_run_id / task_id / operation_id / trace_id
Model call -> request_id / provider_request_id / trace_id
Event -> event id / correlationid / causationid / traceid
DLQ -> original message/event id + trace_id
```

Event payload contents are not correlation metadata and should not be copied into logs.

## 7. Metrics endpoint

`/internal/metrics` is intentionally not an authenticated product API. It contains aggregate telemetry and is designed for an internal scraper.

Production requirements:

- route it only on private/internal network paths or a dedicated internal listener;
- do not expose it through the public ingress;
- prevent public CDN caching/indexing;
- scrape by service identity/network policy;
- retain only bounded labels approved in the metric contract.

The endpoint does not record itself in the HTTP request SLI, preventing scrape traffic from distorting availability/latency.

## 8. Cardinality incident

Symptoms: Prometheus memory/storage growth, expensive queries, unexpectedly high series count.

1. Identify the metric and offending label.
2. Disable/drop the high-cardinality producer/export path if necessary.
3. Never add tenant/user/project/run IDs as a quick debugging label.
4. Move those values to trace attributes or redacted structured logs.
5. Add a regression test to the metric-label allowlist.

`BoundedMetrics` deliberately rejects labels outside the approved vocabulary.

## 9. Cost/provider anomaly

Use Model Gateway telemetry projections and cost ledger as complementary evidence:

- metrics answer rate/latency/error/cost trends using bounded provider/outcome labels;
- traces carry request/run/task/project references;
- cost ledger remains the financial source of truth and must not be replaced by Prometheus counters.

If provider telemetry fails, the paid invocation result and cost-ledger semantics must remain unchanged.

## 10. Local stack lifecycle

```bash
make observability-up
make observability-smoke
make observability-status
make observability-logs
make observability-down
```

The overlay binds local UIs/receivers to `127.0.0.1` by default. Loki and Tempo are local-development backends here; production storage, authentication, TLS, HA, retention and access controls are selected and proven in NODE-72.

## 11. Evidence required to close an observability incident

Record:

- detection source and first impact time;
- affected SLI/SLO and estimated error-budget impact;
- representative correlation/trace IDs, not sensitive content;
- cause and contributing factors;
- mitigation/rollback/fix;
- recovery query or dashboard evidence;
- missing telemetry that delayed diagnosis;
- follow-up test/alert/runbook changes and owner/due date.
