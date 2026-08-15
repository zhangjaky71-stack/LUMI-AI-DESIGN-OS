# NODE-67 — Observability, LangSmith & SRE Telemetry

> Phase: 9 Production Readiness  
> Status: **IN_PROGRESS / BLOCKED_EXTERNAL**  
> Priority: P0 / RELEASE BLOCKER  
> Depends on: NODE-04, NODE-12, NODE-24, NODE-27, NODE-28, NODE-50  
> Produces: OpenTelemetry traces/metrics/log correlation、LangSmith Agent tracing、Dashboards/Alerts/SLO instrumentation

> Implementation Branch: `node-67-observability-release`  
> Release Evidence: `docs/observability/NODE-67-RELEASE-EVIDENCE.md`  
> Signal Contract: `docs/observability/METRICS.md`  
> SLO Baseline: `docs/observability/SLO.md`  
> Runbook: `docs/runbooks/observability.md`  
> Current State: correlation/privacy/local telemetry stack/SLO source baseline implemented; executable validation is blocked by GitHub Actions Billing/spending-limit status and full Python OTel SDK/exporter integration cannot be finalized without correctly regenerating `uv.lock`.

---

## 1. 目标

生产故障不能靠“用户截图 + 猜”。建立从Browser/API/Graph/Agent/Tool/Model/Queue/Worker/DB到Artifact的关联观测，同时控制PII和成本。

OpenTelemetry作为vendor-neutral instrumentation层，统一生成/收集/导出traces、metrics、logs；LangSmith专注Agent/LLM Trace与Eval，不替代基础设施可观测。

## 2. Correlation IDs

每个用户command贯穿：

```text
request_id
trace_id
correlation_id
organization_id
project_id
agent_run_id
task_id
operation_id
provider_request_id
```

日志不用每次全塞全部字段，但关键服务自动context propagation。

当前实现：

- API生成/验证`request_id`、`correlation_id`和W3C `traceparent`；
- Event Envelope已有`correlationid/causationid/traceid`；
- Worker Consumer在handler执行期间绑定event correlation context并在所有退出路径reset；
- Model Gateway已有request/run/task/project/provider refs和`trace_id`投影。

## 3. Traces

Span hierarchy目标：

```text
HTTP POST agent-run
  └─ domain.create_run
  └─ langgraph.run
     └─ task.research
        └─ agent.invoke
           └─ tool.web.search
     └─ task.image
        └─ model_gateway.invoke
           └─ provider.request
```

Queue/message propagation显式传trace context。

当前API correlation layer能够采用已有active OTel trace ID，但仓库锁文件尚无`opentelemetry-*` SDK/exporter依赖，因此完整span creation/OTLP export仍是本节点未完成项，不能把correlation兼容层视为Trace PASS。

## 4. LangSmith

记录目标：agent/model/tool traces、dataset/eval、prompt/agent experiments、latency/token。

LUMI DB保存业务状态/成本/质量摘要与LangSmith trace refs。LangSmith故障不得导致业务run失败，可buffer/drop telemetry按policy。

当前实现：

- `LANGSMITH_TRACING`默认关闭；
- inputs/outputs默认隐藏；
- production privacy validator禁止开启trace同时暴露inputs/outputs；
- API key/endpoint不写入源码生成的环境映射；
- telemetry callback异常不改变业务operation结果。

## 5. Metrics — Golden Signals

API：request_rate/error_rate/latency。当前已实现bounded HTTP counter/histogram和`/internal/metrics`，并用route template避免raw ID cardinality。

Agent/Provider/Queue/Quality/Cost/Security目标信号与状态冻结在`docs/observability/METRICS.md`。没有producer/exporter的signal保持PENDING，不以空dashboard冒充验收。

Model Gateway已实现安全Telemetry Projection和Resilient Sink，provider/outcome可作为bounded metric dimensions；OTel exporter wiring仍待lockfile集成。

## 6. Logs

Structured JSON：

```text
timestamp
level
service
environment
request/trace/run refs
event/error code
safe fields
```

API observability layer默认丢弃Authorization/Cookie/password/prompt/request/response body/signed URL/token/user content等字段，并复用NODE-66 secret redaction。

Collector二次删除已知credential/content telemetry attributes后再送后端。

## 7. Sampling

目标：errors/critical traces高/100%采样；normal high-volume request按rate/adaptive sampling；expensive full Agent traces按环境/privacy policy。

当前sampling policy尚未在真实OTel SDK/Collector生产配置中验证，保持PENDING。不能为了省钱把失败trace采掉。

## 8. Dashboards

目标域：Platform、API/SSE、Agent Runs、Model Providers、Queue/Workers、Database/Cache、Cost & Budget、Design Quality、Security/Auth。

当前Grafana自动provision Prometheus/Tempo/Loki和`LUMI Operational Overview`。只展示已有真实HTTP/Collector signals；其余域必须先接producer再作为Acceptance Evidence。

## 9. Alerts

当前Prometheus bootstrap rules包含：

- API 5xx error rate；
- API P95 latency；
- API metrics missing；
- OTel Collector down；
- OTel metrics exporter down。

生产阶段需基于真实流量升级为multi-window burn-rate并补Agent/provider/queue/DB/cost/security等告警。

## 10. SLO Baseline

已发布`docs/observability/SLO.md`：

```text
Core API rolling-30d availability >= 99.9%
API read/write P95 (excluding long AI work) < 500ms
Agent command accepted P95 < 1s
Realtime status event delivery P95 < 2s
No duplicate paid side effects
```

30日99.9%时间型预算为43分12秒；request-based SLO按bad eligible requests计算。

## 11. Error Budget

已定义分层error-budget policy；SLO修改必须versioned并有证据。Security STOP SHIP不能被可靠性error budget豁免。

## 12. Telemetry Pipeline

本地baseline：

```text
SDK/instrumentation compatibility layer
→ OpenTelemetry Collector
→ Prometheus metrics
→ Tempo traces
→ Loki logs
→ Grafana
```

Collector、Prometheus、Tempo、Loki、Grafana均已版本化进`docker-compose.observability.yml`，端口默认只绑定localhost，并提供`make observability-*`生命周期和smoke脚本。

应用层完整OTel SDK/OTLP exporter仍待正确加入Python依赖和`uv.lock`。

## 13. Frontend

目标：route errors、Canvas crashes、API failures、Web Vitals/interaction perf、correlation/request id；不自动上传用户内容/Canvas截图。

状态：PENDING。

## 14. Synthetic Checks

当前完成本地Observability backend readiness smoke。homepage/login/create-read synthetic project/no-cost agent/storage roundtrip等应用synthetic checks仍PENDING。

真实付费AI synthetic probe必须低频且有预算。

## 15. Tests

新增/扩展：

```text
apps/api/tests/test_observability.py
apps/agent-runtime/tests/test_observability.py
services/model-gateway/tests/test_observability.py
apps/worker-media/tests/test_event_runtime.py
```

覆盖traceparent、ID sanitization、log redaction、cardinality guard、scrape self-exclusion、LangSmith outage、Model telemetry outage、safe provider projection、HTTP→event/worker correlation binding/reset。

`.github/workflows/observability-contract.yml`负责未来runner恢复后的source tests + Compose/backend readiness + Prometheus rule validation。

## 16. 验收标准

- [ ] Trace可从request追到provider/artifact。
- [x] OTel架构保持vendor-neutral，Collector作为backend fan-out boundary。
- [x] LangSmith与业务observability分工和failure isolation明确。
- [ ] 关键dashboard/alerts在运行环境实际工作。
- [x] source-level logs默认禁止secrets/prompt/content并有回归测试。
- [x] SLO与error budget baseline发布。
- [ ] Full OTel SDK/exporter和lockfile集成完成。
- [ ] Frontend/DB/Queue metrics/Quality/Cost/Security生产者达到验收范围。
- [ ] Observability Contract workflow在最新HEAD执行全绿。

### 16.1 当前外部阻塞 — 2026-08-15

GitHub Actions当前不能分配runner，平台提示recent account payments failed或Actions spending limit需要提高。该问题已在NODE-66多次复现，job在执行任何step前结束。因此NODE-67 workflow尚无运行PASS/FAIL证据。

另外，当前`uv.lock`包含LangSmith但不存在`opentelemetry-*`包。无法执行lock regeneration时禁止手工伪造锁文件；恢复可执行环境后应显式加入兼容OTel dependencies、运行`uv lock/sync --frozen`、完成OTLP export integration并重新验收。

## 17. Definition of Done

```text
observability stack operational
+ trace/log/metric correlation green
+ alert/SLO runbook tested
```

当前DoD：**NOT MET / IN PROGRESS**。

下一节点：NODE-68 Recovery。NODE-68可按外部阻塞策略继续工程实现，但NODE-71/72不得把NODE-67视为Production Observability PASS，直到Release Evidence中的运行时门禁全部完成。
