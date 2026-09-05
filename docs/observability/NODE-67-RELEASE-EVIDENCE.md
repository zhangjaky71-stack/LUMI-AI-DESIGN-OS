# NODE-67 — Observability Release Evidence

Status: **IN PROGRESS / EXECUTION EVIDENCE BLOCKED**  
Date: 2026-08-15  
Branch: `node-67-observability-release`

## 1. Decision

NODE-67 is not COMPLETE. A substantial source baseline is implemented, but the Definition of Done requires an operational telemetry stack, end-to-end exported traces/metrics/logs and tested alerts/runbooks. GitHub Actions runner allocation is still blocked by the account Billing / Actions spending-limit condition inherited from NODE-66. NODE-66 also discovered a stale `uv.lock`; NODE-67 now treats `uv lock --check` as a prerequisite and cannot complete full Python OTel SDK/exporter integration until the lock can be regenerated and reviewed correctly.

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
| Worker current correlation context | Worker observability + consumer binding/reset | IMPLEMENTED |
| Browser route/runtime error capture | browser telemetry contract + global client lifecycle | IMPLEMENTED; execution pending |
| Canvas captured-error projection | Canvas Engine initialization catch → fixed telemetry code | IMPLEMENTED; execution pending |
| Browser Web Vitals | TTFB/LCP/CLS/INP privacy-safe sampled events | IMPLEMENTED; backend aggregation pending |
| Failed API correlation | `observedFetch` projects request/correlation response headers only | IMPLEMENTED; adoption/runtime pending |
| Browser telemetry intake | same-origin Next route, byte cap, re-sanitization | IMPLEMENTED; runtime pending |
| Local Collector | `infra/observability/otel-collector.yaml` | CONFIGURED |
| Local Prometheus | config + alert rules | CONFIGURED |
| Local Tempo | upstream-aligned 3.0.3 single-binary shape | CONFIGURED |
| Local Loki OTLP logs | Loki config + Collector `otlphttp/loki` | CONFIGURED |
| Local Grafana | datasource/dashboard provisioning | CONFIGURED |
| One-command lifecycle | Makefile + `scripts/observability-smoke` | IMPLEMENTED |
| Zero-cost staging synthetic | homepage + API readiness + correlation header probe | IMPLEMENTED; staging variables/run pending |
| SLO/error budget | `docs/observability/SLO.md` | PUBLISHED AS BASELINE |
| Signal contract | `docs/observability/METRICS.md` | PUBLISHED |
| Incident/runbook | `docs/runbooks/observability.md` | PUBLISHED |

## 3. Tests added/extended

```text
apps/api/tests/test_observability.py
apps/agent-runtime/tests/test_observability.py
services/model-gateway/tests/test_observability.py
apps/worker-media/tests/test_event_runtime.py
apps/web/src/lib/observability/browser.test.ts
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
- Worker correlation binding/reset, including DB-connect failure;
- browser route ID/query removal;
- browser safe request/correlation IDs;
- browser unknown content field dropping so prompt/stack/message/Canvas/auth data cannot pass the source contract;
- bounded browser status/value dimensions.

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

The repository lockfile currently contains LangSmith transitively through Deep Agents, but no `opentelemetry-*` packages. NODE-67 therefore does not pretend that its compatibility hooks are complete SDK instrumentation.

The root security/observability gates now require:

```bash
uv lock --check
uv sync --all-packages --frozen
```

Required before COMPLETE:

1. restore an executable development/CI environment;
2. regenerate/review the stale workspace lock with pinned uv rather than hand-editing it;
3. add explicit compatible OTel API/SDK/exporter/instrumentation dependencies;
4. regenerate/review `uv.lock` again for the OTel dependency change;
5. wire OTLP export to Collector;
6. prove HTTP → event/worker → Agent/Model/Tool/provider spans in Tempo or equivalent backend.

## 6. Browser/frontend privacy and cardinality evidence

The browser implementation deliberately does **not** use a third-party error SDK or upload raw exceptions. Its accepted envelope contains only:

```text
kind (closed enum)
name (bounded code)
normalized route without query/hash and with opaque IDs replaced
bounded numeric value
HTTP status class
safe request_id / correlation_id
bounded error code
```

It does not serialize error message, stack, prompt/output, request/response body, Canvas data/screenshot, Authorization/Cookie, signed URL or file contents. Errors/API failures are sampled at 100%; performance/Web Vitals default to 10% sampling.

`/api/telemetry/browser` is same-origin, JSON-only, byte-capped and re-sanitizes the event before structured logging. This remains **source evidence**, not a claim that the logs are already queryable in Loki in staging.

## 7. Synthetic checks

`.github/workflows/observability-synthetic.yml` provides a zero-AI-cost scheduled/manual probe. When public staging variables are configured it verifies:

- homepage responds over public HTTPS;
- API `/health/ready` succeeds and reports `status=ok`;
- API response includes bounded `X-Request-ID`, `X-Correlation-ID` and W3C `traceparent`;
- initial DNS results are public/non-reserved;
- redirects are not followed, preventing a public target from turning the runner into an internal-network redirect probe.

This does **not** yet satisfy login/create-read project/storage roundtrip synthetics. Those require staging credentials/data lifecycle design and remain pending. Paid-model synthetics remain deliberately absent from the frequent probe.

## 8. Current signal gaps

- Full OTel SDK span/exporter wiring.
- Browser telemetry backend aggregation/dashboard linkage (source intake exists, LIVE backend query does not).
- Broad adoption of `observedFetch` across all frontend API clients.
- Agent run/task/approval metrics exporter.
- Queue depth/oldest-age/retry/DLQ metric producer/exporter.
- DB connection/query/cache saturation signals.
- Cost/Budget operational metrics from canonical ledger.
- Visual Critic/Auto Repair quality metrics.
- Security/Auth aggregate operational metrics.
- Product/business event metrics.
- Authenticated create/read project and storage-roundtrip synthetics.
- Production sampling/tail-sampling policy validation.
- Production retention/access-control/storage design.

The metric contract lists intended signal names/status and prevents these gaps from being hidden by empty dashboards.

## 9. Runtime validation blockers

### GitHub Actions

Repository Actions jobs currently fail before runner allocation because GitHub reports recent account payment failure or an Actions spending-limit issue. This must be resolved externally, after which NODE-67 tests and config validation must run on the latest head.

### Python lock

NODE-66 review established that the checked-in `uv.lock` is stale relative to current manifests. Observability workflow now checks lock freshness before frozen install. The lock must be regenerated/reviewed with the pinned uv version; hand-editing it is not acceptable evidence.

### Local backend execution

This implementation session has not executed Docker Compose against the user's Docker Desktop. `docker compose config`, backend readiness endpoints, dashboard provisioning and end-to-end OTLP export therefore remain unproven until `make observability-up && make observability-smoke` runs successfully in an executable environment.

## 10. Remaining acceptance gates

- [ ] `uv lock --check` green after a reviewed lock refresh.
- [ ] All Python observability tests green on latest head.
- [ ] Browser telemetry Vitest, web typecheck and lint green.
- [ ] Ruff format/lint and Pyright green.
- [ ] `docker compose ... config` validates the observability overlay.
- [ ] `make observability-smoke` green.
- [ ] OTel SDK/exporter dependency + lockfile integration complete.
- [ ] Request trace visible end-to-end through asynchronous and model/provider boundaries.
- [ ] Prometheus API/collector metrics queryable.
- [ ] Loki sanitized logs queryable and linked to Tempo by trace ID.
- [ ] Browser telemetry can be queried in the chosen backend without content/ID-cardinality leakage.
- [ ] Grafana provisioning loads datasources/dashboard without manual setup.
- [ ] Alert rules evaluate successfully; at least one controlled firing/recovery is demonstrated.
- [ ] LangSmith enabled in a test environment with hidden inputs/outputs and outage test preserved.
- [ ] Zero-cost staging synthetic executes successfully with configured staging URLs.
- [ ] Authenticated project/storage synthetics are designed and validated or explicitly deferred with owner.
- [ ] Required dashboard domains have real producers or are explicitly deferred with owner/next node.
- [ ] SLO/error-budget queries validated against staging traffic.
- [ ] Runbook smoke/incident drill recorded.

## 11. Transition rule

NODE-68 engineering may proceed only if dependency policy permits carrying NODE-67 as an explicit external/execution blocker. NODE-71 staging acceptance and NODE-72 production deployment must not treat NODE-67 as PASS until the runtime gates above are satisfied.
