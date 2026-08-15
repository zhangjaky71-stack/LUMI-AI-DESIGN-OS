# NODE-67 — Observability, LangSmith & SRE Telemetry

> Phase: 9 Production Readiness  
> Status: **IN_PROGRESS / RELEASE_BLOCKED**  
> Priority: P0 / RELEASE BLOCKER  
> Depends on: NODE-04, NODE-12, NODE-24, NODE-27, NODE-28, NODE-50  
> Produces: OpenTelemetry traces/metrics/log correlation、LangSmith Agent tracing、Dashboards/Alerts/SLO instrumentation

> Implementation Branch: `node-67-observability-release`  
> Release Evidence: `docs/observability/NODE-67-RELEASE-EVIDENCE.md`  
> Signal Contract: `docs/observability/METRICS.md`  
> SLO Baseline: `docs/observability/SLO.md`  
> Runbook: `docs/runbooks/observability.md`  
> Current State: API/Agent/Worker/Model correlation、privacy-safe logs、bounded metrics、browser telemetry source、local telemetry stack、zero-cost staging synthetic、SLO/runbook source baseline均已实现；完整 OTel SDK/OTLP span export、真实backend查询、dashboard/alert演练与运行时验收仍被 stale `uv.lock` 和 GitHub Actions Billing/spending-limit 阻塞。

---

## 1. 目标

生产故障不能靠“用户截图 + 猜”。建立从 Browser/API/Graph/Agent/Tool/Model/Queue/Worker/DB 到 Artifact 的关联观测，同时控制 PII、内容泄露、高基数与成本。

OpenTelemetry 作为 vendor-neutral instrumentation 层，统一生成/收集/导出 traces、metrics、logs；LangSmith 专注 Agent/LLM Trace 与 Eval，不替代基础设施可观测。

## 2. Correlation IDs

每个用户 command 贯穿：

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

当前实现：

- API 生成/验证 `request_id`、`correlation_id` 和 W3C `traceparent`；
- API response 回写 `X-Request-ID`、`X-Correlation-ID`、`traceparent`；
- Event Envelope 已有 `correlationid/causationid/traceid`；
- Worker Consumer 在 handler 执行期间绑定 event correlation context，并在所有退出路径 reset；
- Model Gateway 已有 request/run/task/project/provider refs 和 `trace_id` 安全投影；
- Browser `observedFetch` 可从失败 API response 读取 request/correlation IDs，不读取 response body。

## 3. Traces

目标 span hierarchy：

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

Queue/message propagation 显式携带 trace context。

当前 API correlation layer 能够采用已有 active OTel trace ID，但仓库锁文件尚无完整 `opentelemetry-*` SDK/exporter 依赖，因此完整 span creation/OTLP export 仍为 PENDING。Correlation compatibility 不能被当作 Trace PASS。

## 4. LangSmith

目标记录：agent/model/tool traces、dataset/eval、prompt/agent experiments、latency/token。

LUMI DB 保存业务状态/成本/质量摘要与 LangSmith trace refs。LangSmith 故障不得导致业务 run 失败，可按 policy buffer/drop telemetry。

当前实现：

- `LANGSMITH_TRACING` 默认关闭；
- inputs/outputs 默认隐藏；
- production privacy validator 禁止 tracing 开启同时暴露 inputs/outputs；
- API key/endpoint 不写入源码生成的环境映射；
- telemetry callback 异常不改变业务 operation 结果。

## 5. Metrics — Golden Signals

API：request rate / error rate / latency。当前已实现 bounded HTTP counter/histogram 和 `/internal/metrics`，并用 route template 避免 raw ID cardinality。

Agent/Provider/Queue/Quality/Cost/Security/Browser 的目标信号与状态冻结在 `docs/observability/METRICS.md`。没有 producer/exporter 的 signal 保持 PENDING，不以空 dashboard 冒充验收。

Model Gateway 已实现安全 Telemetry Projection 和 Resilient Sink；provider/outcome 可作为 bounded metric dimensions，OTel exporter wiring 仍待 lockfile 集成。

## 6. Logs & Privacy

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

API observability layer 默认丢弃 Authorization/Cookie/password/prompt/request/response body/signed URL/token/user content，并复用 NODE-66 secret redaction。

Browser telemetry 只接受 closed enum event kind、bounded name/error code、normalized route、bounded numeric value、status class、safe request/correlation refs。以下内容禁止进入 browser telemetry：

```text
error message / stack
query string / hash
prompt / model output
Canvas content / screenshot
request / response body
Authorization / Cookie
signed URL
file contents
```

同源 Next intake 会再次 sanitize 并限制 body size；Collector 再次删除已知 credential/content attributes 后才允许送后端。

## 7. Sampling

目标：errors/critical traces 高/100%采样；normal high-volume request 按 rate/adaptive sampling；expensive full Agent traces 按环境/privacy policy。

Browser source baseline：

```text
errors / API failures = 100%
Web Vitals / performance = 10%
```

真实 OTel tail/adaptive sampling 尚未在 Collector/生产流量验证，保持 PENDING。不能为了省钱把失败 trace 采掉。

## 8. Dashboards

目标域：Platform、API/SSE、Agent Runs、Model Providers、Queue/Workers、Database/Cache、Cost & Budget、Design Quality、Security/Auth、Frontend UX。

当前 Grafana 自动 provision Prometheus/Tempo/Loki 和 `LUMI Operational Overview`。只展示已有真实 HTTP/Collector signals；其余域必须先接 producer 再作为 Acceptance Evidence。

## 9. Alerts

当前 Prometheus bootstrap rules 包含：

- API 5xx error rate；
- API P95 latency；
- API metrics missing；
- OTel Collector down；
- OTel metrics exporter down。

生产阶段需基于真实流量升级为 multi-window burn-rate，并补 Agent/provider/queue/DB/cost/security/browser 等告警。

## 10. SLO Baseline

已发布 `docs/observability/SLO.md`：

```text
Core API rolling-30d availability >= 99.9%
API read/write P95 (excluding long AI work) < 500ms
Agent command accepted P95 < 1s
Realtime status event delivery P95 < 2s
No duplicate paid side effects
```

30 日 99.9% 时间型预算为 43 分 12 秒；request-based SLO 按 bad eligible requests 计算。

## 11. Error Budget

已定义分层 error-budget policy；SLO 修改必须 versioned 并有证据。Security STOP SHIP 不能被可靠性 error budget 豁免。

## 12. Telemetry Pipeline

本地 baseline：

```text
SDK/instrumentation compatibility layer
→ OpenTelemetry Collector
→ Prometheus metrics
→ Tempo traces
→ Loki logs
→ Grafana
```

Collector、Prometheus、Tempo、Loki、Grafana 均已版本化进 `docker-compose.observability.yml`，端口默认只绑定 localhost，并提供 `make observability-*` 生命周期与 smoke 脚本。

应用层完整 OTel SDK/OTLP exporter 仍待正确加入 Python dependencies 并重新生成/审核 `uv.lock`。

## 13. Frontend

已实现 source baseline：

```text
apps/web/src/lib/observability/browser.ts
apps/web/src/components/BrowserObservability.tsx
apps/web/src/app/api/telemetry/browser/route.ts
```

能力：

- window runtime error / unhandled rejection；
- React route boundary error；
- Canvas 捕获型初始化错误；
- TTFB / LCP / CLS / INP；
- failed API response 的 request/correlation IDs；
- route ID/query normalization；
- same-origin intake + byte cap + server-side re-sanitization。

Frontend source tests 覆盖隐私字段丢弃、route normalization、cross-origin rejection、oversize rejection 和 structured log 安全性。

状态：**SOURCE IMPLEMENTED / RUNTIME BACKEND AGGREGATION PENDING**。广泛把现有 API client 迁移到 `observedFetch` 仍需继续完成。

## 14. Synthetic Checks

已有两层：

1. 本地 Observability backend readiness smoke；
2. `.github/workflows/observability-synthetic.yml` 每 10 分钟（配置 staging vars 后）或手工执行的零付费 AI synthetic。

当前 staging synthetic 验证：

```text
public HTTPS homepage
API /health/ready
status=ok
X-Request-ID
X-Correlation-ID
traceparent
```

目标 URL 先做 DNS/public-IP 验证且不跟随 redirect，避免把 runner 变成 SSRF/internal-network probe。

login/create-read project/storage roundtrip 等 authenticated synthetic 仍 PENDING；真实付费 AI synthetic 必须低频且有预算，当前高频 probe 不调用模型。

## 15. Tests / CI

Python：

```text
apps/api/tests/test_observability.py
apps/agent-runtime/tests/test_observability.py
services/model-gateway/tests/test_observability.py
apps/worker-media/tests/test_event_runtime.py
```

Frontend：

```text
apps/web/src/lib/observability/browser.test.ts
apps/web/src/app/api/telemetry/browser/route.test.ts
```

覆盖 traceparent、ID sanitization、log redaction、cardinality guard、scrape self-exclusion、LangSmith outage、Model telemetry outage、safe provider projection、HTTP→event/worker correlation binding/reset、browser privacy、same-origin intake。

`.github/workflows/observability-contract.yml` 在 runner 恢复后执行 Python contract、browser Vitest/typecheck/lint、Compose/backend readiness、dashboard JSON、Prometheus config/rules validation，并在 Python install 前执行 `uv lock --check`。

## 16. 验收标准

- [ ] Trace 可从 request 追到 provider/artifact。
- [x] OTel 架构保持 vendor-neutral，Collector 作为 backend fan-out boundary。
- [x] LangSmith 与业务 observability 分工和 failure isolation 明确。
- [ ] 关键 dashboard/alerts 在运行环境实际工作。
- [x] source-level logs 默认禁止 secrets/prompt/content 并有回归测试。
- [x] Browser source telemetry 隐私/基数 contract 已实现并纳入 CI。
- [x] 零 AI 成本 staging synthetic source 已实现。
- [x] SLO 与 error budget baseline 发布。
- [ ] Full OTel SDK/exporter 和 lockfile 集成完成。
- [ ] Browser telemetry backend aggregation/query 完成。
- [ ] DB/Queue metrics/Quality/Cost/Security 等生产者达到验收范围或有明确 owner/defer decision。
- [ ] Observability Contract workflow 在最新 HEAD 执行全绿。
- [ ] Staging Synthetic 在真实 staging URL 执行全绿。

### 16.1 当前阻塞 — 2026-08-15

1. GitHub Actions 当前不能分配 runner，平台提示 recent account payments failed 或 Actions spending limit 需要提高；job 在执行任何 step 前结束。
2. NODE-66 已确认当前 `uv.lock` 与 workspace manifests 漂移；NODE-67 workflow 已加入 `uv lock --check`。必须用 pinned uv `0.11.28` 正常 regenerate/review lock，禁止手工伪造。
3. 当前 `uv.lock` 尚无完整 `opentelemetry-*` SDK/exporter 依赖。恢复可执行环境后再加入兼容 OTel dependencies、重新 lock、完成 OTLP export integration 并重新验收。

## 17. Definition of Done

```text
observability stack operational
+ trace/log/metric correlation green
+ frontend/browser signal queryable
+ synthetic green
+ alert/SLO runbook tested
```

当前 DoD：**NOT MET / IN PROGRESS / RELEASE BLOCKED**。

下一节点：NODE-68 Recovery。NODE-68 可按外部阻塞策略继续工程实现，但 NODE-71/72 不得把 NODE-67 视为 Production Observability PASS，直到 Release Evidence 中的运行时门禁全部完成。
