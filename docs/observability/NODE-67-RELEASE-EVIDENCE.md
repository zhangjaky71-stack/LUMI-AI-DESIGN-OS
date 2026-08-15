# NODE-67 — Observability Release Evidence

Status: **IN PROGRESS / EXECUTION EVIDENCE BLOCKED**  
Date: 2026-08-15  
Branch: `node-67-observability-release`

## 1. Decision

NODE-67 is not COMPLETE. A substantial source baseline is implemented, but the Definition of Done requires an operational telemetry stack, end-to-end exported traces/metrics/logs and tested alerts/runbooks. GitHub Actions runner allocation is still blocked by the account Billing / Actions spending-limit condition inherited from NODE-66, and this environment cannot regenerate `uv.lock` after adding new OpenTelemetry SDK packages.

No source-only configuration is counted as runtime PASS evidence.

## 2. Implemented source evidence

| Capability | Evidence | State |
|---|---|---|
| HTTP request/correlation IDs | `apps/api/src/lumi_api/observability` | IMPLEMENTED |
| W3C traceparent compatibility | API observability core/middleware | IMPLEMENTED; full SDK spans pending |
| Privacy-safe structured logs | API observability core | IMPLEMENTED |
| High-cardinality guard | `BoundedMetrics` + tests | IMPLEMENTED |
| API request/error/latency metrics | `BoundedMetrics` + `/internal/metrics` | IMPLEMENTED |
| Metrics scrape self-exclusion | observability middleware | IMPLEMENTED |
| Agent LangSmith privacy policy | `apps/agent-runtime/src/lumi_agent_runtime/observability.py` | IMPLEMENTED |
| LangSmith outage isolation | `best_effort_*` + tests | IMPLEMENTED |
| Model telemetry outage isolation | `ResilientCostTelemetrySink` | IMPLEMENTED |
| Model provider safe telemetry projection | Model Gateway telemetry projection | IMPLEMENTED |
| Event envelope trace/correlation fields | existing NODE-12/19 event runtime | EXISTING/CANONICAL |
| Worker current correlation context | Worker observability + consumer binding | IMPLEMENTED |
| Local Collector | `infra/observability/otel-collector.yaml` | CONFIGURED |
| Local Prometheus | config + alert rules | CONFIGURED |
| Local Tempo | upstream-aligned 3.0.3 single-binary shape | CONFIGURED |
| Local Loki OTLP logs | Loki config + Collector `otlphttp/loki` | CONFIGURED |
| Local Grafana | datasource/dashboard provisioning | CONFIGURED |
| One-command lifecycle | Makefile + `scripts/observability-smoke` | IMPLEMENTED |
| SLO/error budget | `docs/observability/SLO.md` | PUBLISHED AS BASELINE |
| Signal contract | `docs/observability/METRICS.md` | PUBLISHED |
| Incident/runbook | `docs/runbooks/observability.md` | PUBLISHED |

## 3. Tests added/extended

```text
apps/api/tests/test_observability.py
apps/agent-runtime/tests/test_observability.py
services/model-gateway/tests/test_observability.py
apps/worker-media/tests/test_event_runtime.py
```

Coverage includes:

- valid/invalid traceparent handling;
- request/correlation ID sanitization;
- prompt/Authorization/signed-URL log exclusion and secret redaction;
- high-cardinality metric label rejection;
- normalized HTTP route metrics;
- scrape endpoint exclusion from API SLI;
- telemetry logging outage isolation;
- LangSmith privacy defaults and outage isolation;
- Model Gateway telemetry outage isolation and safe projection;
- Outbox trace ID propagation;
- Worker correlation binding/reset, including DB-connect failure.

These tests are source evidence only until they execute successfully on the latest branch head.

## 4. Local observability stack

Expected lifecycle:

```bash
make observability-up
make observability-smoke
make observability-status
make observability-logs
make observability-down
```

Components:

```text
OpenTelemetry Collector
Prometheus
Tempo
Loki
Grafana
```

Local ports bind to `127.0.0.1` by default. Grafana provisions Prometheus, Tempo and Loki plus a truthful operational overview that only treats existing producers as live signals.

## 5. OTel SDK / lockfile constraint

The repository lockfile currently contains LangSmith transitively through Deep Agents, but no `opentelemetry-*` packages. NODE-67 therefore does not edit Python dependency manifests without regenerating `uv.lock`.

Current API code can adopt an active OpenTelemetry trace ID if the API package exists in the deployment, but that compatibility hook is **not** equivalent to full OpenTelemetry SDK instrumentation.

Required before COMPLETE:

1. restore an executable development/CI environment;
2. add explicit compatible OTel API/SDK/exporter/instrumentation dependencies;
3. regenerate and review `uv.lock` rather than hand-editing it;
4. wire OTLP export to Collector;
5. prove HTTP → event/worker → Agent/Model/Tool/provider spans in Tempo or equivalent backend.

## 6. Current signal gaps

- Full OTel SDK span/exporter wiring.
- Frontend route error/Web Vitals/correlation instrumentation.
- Agent run/task/approval metrics exporter.
- Queue depth/oldest-age/retry/DLQ metric producer/exporter.
- DB connection/query/cache saturation signals.
- Cost/Budget operational metrics from canonical ledger.
- Visual Critic/Auto Repair quality metrics.
- Security/Auth aggregate operational metrics.
- Product/business event metrics.
- Synthetic checks beyond local backend smoke.
- Production sampling/tail-sampling policy validation.
- Production retention/access-control/storage design.

The metric contract lists intended signal names/status and prevents these gaps from being hidden by empty dashboards.

## 7. Runtime validation blockers

### GitHub Actions

Repository Actions jobs currently fail before runner allocation because GitHub reports recent account payment failure or an Actions spending-limit issue. This must be resolved externally, after which NODE-67 tests and config validation must run on the latest head.

### Local backend execution

This implementation session has not executed Docker Compose against the user's Docker Desktop. `docker compose config`, backend readiness endpoints, dashboard provisioning and end-to-end OTLP export therefore remain unproven until `make observability-up && make observability-smoke` runs successfully in an executable environment.

## 8. Remaining acceptance gates

- [ ] All new Python tests green on latest head.
- [ ] Ruff format/lint and Pyright green.
- [ ] `docker compose ... config` validates the observability overlay.
- [ ] `make observability-smoke` green.
- [ ] OTel SDK/exporter dependency + lockfile integration complete.
- [ ] Request trace visible end-to-end through asynchronous and model/provider boundaries.
- [ ] Prometheus API/collector metrics queryable.
- [ ] Loki sanitized logs queryable and linked to Tempo by trace ID.
- [ ] Grafana provisioning loads datasources/dashboard without manual setup.
- [ ] Alert rules evaluate successfully; at least one controlled firing/recovery is demonstrated.
- [ ] LangSmith enabled in a test environment with hidden inputs/outputs and outage test preserved.
- [ ] Required dashboard domains have real producers or are explicitly deferred with owner/next node.
- [ ] SLO/error-budget queries validated against staging traffic.
- [ ] Runbook smoke/incident drill recorded.

## 9. Transition rule

NODE-68 engineering may proceed only if dependency policy permits carrying NODE-67 as an explicit external/execution blocker. NODE-71 staging acceptance and NODE-72 production deployment must not treat NODE-67 as PASS until the runtime gates above are satisfied.
