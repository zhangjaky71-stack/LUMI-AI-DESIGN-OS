# NODE-67 — Observability Implementation Report

Status: **CORE_IMPLEMENTED_VALIDATING_NOT_COMPLETE**  
Current stacked base: `feat/node-66-security-hardening`  
Current stacked head: `feat/node-67-observability`

## 1. Implemented current-track core

### Canonical request/trace correlation

The existing Request ID middleware is upgraded rather than replaced.

HTTP requests now have one bounded correlation model:

- `request_id`
- `correlation_id`
- W3C-style `traceparent` continuation
- bounded `tracestate`
- one server child span id

Invalid client trace context fails as a bounded 400. Business exceptions are outside trace-context parsing and keep their original semantics.

Authenticated `RequestContext` uses the middleware-generated request ID and actual 32-character trace ID rather than re-reading raw headers.

### Business correlation refs

Telemetry context can carry:

- `organization_id`
- `project_id`
- `agent_run_id`
- `task_id`
- `operation_id`
- `provider_request_id`

These are trace/log drill-down dimensions. They are intentionally forbidden as default metric labels.

### HTTP → Event/Outbox propagation

The existing canonical `EventEnvelope` is extended additively with optional:

- `request_id`
- `tracestate`

Its existing `correlation_id` and `traceparent` remain canonical.

`new_event()` inherits the active telemetry context when explicit values are absent. Existing Outbox serialization already writes the entire envelope, so no second message envelope or database table is introduced.

A message-context helper creates the consumer child trace context from those fields. Production workers still need to compose it and remain a P0 gap.

### Safe telemetry records

Vendor-neutral contracts are implemented for:

- spans;
- metrics;
- structured logs.

Safety controls:

- fixed low-cardinality metric attribute allowlist;
- organization/project/run/task/operation IDs rejected as metric labels;
- prompt/content/password/Authorization/token/secret/cookie/API-key/signed-URL/reasoning fields rejected from telemetry attributes;
- secret-shaped scalar values are rejected;
- bounded attribute count/key/value sizes;
- timestamps must be timezone-aware.

### Fail-open exporter boundary

`SafeTelemetry` catches sink/exporter exceptions. `SafeLangSmithTracer` similarly catches optional LangSmith failures. Observability failure cannot become a business availability dependency.

### Sampling

Normal traces use deterministic trace-id sampling with a 10% default baseline. Error/critical/forced evidence is always sampled.

### Structured JSON logs

The API composes `PythonJsonLoggingSink` immediately. It writes validated `StructuredLogRecord` objects through the standard Python logging pipeline as compact JSON.

The default sink intentionally does **not** pretend to export traces or metrics; production OpenTelemetry/Collector composition remains explicit.

### HTTP telemetry

The Request middleware records best-effort:

- HTTP server span;
- `http.server.duration_ms` metric with route template/method/status class/outcome;
- structured `http.request.completed` log.

Raw resource-id URL paths are not used as metric labels; route templates are used instead.

### SLO / dashboard / alert policy

Machine-readable policy artifacts are implemented:

- `slo-policy.json`
- `dashboard-spec.json`
- `alert-policy.json`

They define the intended operational contract without claiming deployed dashboards or alert routing.

## 2. NODE-66 compatibility

NODE-67 found a middleware-ordering edge case: the outer Request/Trace boundary can create a 400 before the inner NODE-66 Security middleware returns a response. A final outer response-header enforcement middleware now guarantees NODE-66 CSP/nosniff/frame/referrer/permissions/HSTS policy also applies to correlation/idempotency short-circuit responses.

Development Swagger/ReDoc keeps its dedicated restricted docs CSP when already set. Production still uses the NODE-66 HSTS baseline.

## 3. Existing truth layers deliberately reused

NODE-67 does not create competing operational truth.

- NODE-57 remains the user-visible Agent Timeline and Run UX truth.
- AgentRun/Task/Approval/Artifact state remains in their domain engines.
- NODE-27 Cost Ledger remains cost truth.
- NODE-65 Audit remains governance/security fact truth.
- Existing EventEnvelope/Outbox remains queue propagation truth.

Observability is correlation and telemetry, not a second state machine.

## 4. OpenTelemetry / Collector boundary

The current workspace does not contain OpenTelemetry Python SDK/exporter dependencies. NODE-67 deliberately does not edit dependency manifests without regenerating and reviewing `uv.lock`, because NODE-66 makes lock consistency a security gate.

Production must add a reviewed OTel/OTLP adapter and Collector deployment with:

- batching;
- retry/backoff;
- memory/backpressure limits;
- filtering/redaction;
- trace/metric export;
- exporter-drop telemetry;
- HA/retention/privacy policy.

Until that exists, `NODE67-GAP-101` stays open.

## 5. LangSmith boundary

LangSmith is treated as optional Agent/LLM trace/eval fan-out, not infrastructure observability or business state.

The implemented port is fail-open. A production adapter/OTel fan-out and evaluation integration remain open.

## 6. Cardinality policy

Metric labels are constrained to a fixed allowlist such as:

```text
service
environment
http.method
http.route
http.status_class
outcome
provider
model_family
capability
queue
worker
operation_type
error_code
```

High-cardinality IDs are trace/log fields only.

## 7. SLO baseline

Current policy baseline:

- Core synchronous API availability: 99.9% / 30d;
- Core synchronous read/write p95: <500ms;
- Agent command accepted/persisted p95: <1s;
- realtime state-delivery p95: <2s;
- duplicate paid side effects: zero.

These are baseline policy definitions, not claims about observed production performance.

## 8. Current production gaps

Source of truth: `reports/nodes/NODE-67/gap-ledger.json`.

Open P0 groups include:

1. production OpenTelemetry SDK/OTLP + Collector;
2. production queue consumer continuation;
3. Graph/Agent/Task/Tool/Model/provider/worker/database span instrumentation;
4. real LangSmith adapter/eval fan-out;
5. non-HTTP metric producers;
6. deployed dashboards/data sources;
7. alert routing/on-call/runbooks/drills;
8. structured logging adoption across all services;
9. frontend Web Vitals/browser correlation;
10. synthetic checks;
11. production SLO/error-budget measurement;
12. telemetry retention/privacy/cardinality/backpressure governance;
13. latest-head hosted validation.

## 9. Explicit non-claims

This implementation does **not** currently claim:

- OpenTelemetry Collector is deployed;
- traces/metrics are exported to a production backend;
- every worker continues EventEnvelope trace context;
- complete Agent/Tool/Model/provider distributed traces;
- LangSmith production integration is active;
- all Golden Signal metrics exist;
- dashboards are deployed or accurate against production data;
- alerts route to real on-call owners;
- Web Vitals/synthetics are live;
- production SLO targets are being met;
- all services emit structured safe logs;
- hosted CI is green.

NODE-67 remains **NOT COMPLETE** until the open P0 ledger closes with executed evidence.
