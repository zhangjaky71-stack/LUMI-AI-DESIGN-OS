# NODE-05 — Benchmark Harness

> Phase: 0 Benchmark Before Build  
> Status: **COMPLETE**  
> Implementation Status: **COMPLETE**  
> Implemented Commit: `573a0d82e4f9deaed5252be1e943a5954b71355a`  
> Implementation PR: `#3`  
> Acceptance Report: `reports/nodes/NODE-05/acceptance.md`  
> Clean Acceptance CI: `31591585790`  
> Benchmark Artifact: `9139339839`  
> Implemented At: `2026-08-12`  
> Priority: P0  
> Depends on: NODE-02, NODE-04  
> Produces: LUMI 统一离线/在线评测框架、数据集规范、Release Gate 接口

---

## 1. 目标

在大量 Agent、Prompt、模型和设计功能开发之前先建立评测系统。后续任何“效果更好”的结论必须能够被数据证明，而不是凭聊天演示或主观感觉。

Benchmark Harness 必须同时覆盖：

```text
deterministic software tests
+ agent trajectory eval
+ model quality eval
+ visual/design eval
+ recovery/reliability eval
+ cost/latency eval
```

NODE-05 只建立框架、fixture、runner、report 和 release gate；具体能力数据集由后续 Node 持续补充。

## 2. 目录

```text
evals/
├─ README.md
├─ pyproject.toml
├─ datasets/
│  ├─ smoke/
│  ├─ brief/
│  ├─ planning/
│  ├─ tool-use/
│  ├─ constraints/
│  ├─ design-ir/
│  ├─ visual/
│  ├─ brand/
│  └─ recovery/
├─ fixtures/
│  ├─ projects/
│  ├─ assets/
│  └─ provider-responses/
├─ graders/
│  ├─ deterministic/
│  ├─ llm/
│  └─ visual/
├─ runners/
├─ reports/
└─ schemas/
```

P0 实现允许先将 runner/grader modules 扁平化到 `evals/`，但 dataset / fixture / schema / report 边界必须保持，后续 grader 类型增加时再物理拆分子包。

## 3. Case Schema

每个 eval case 至少：

```yaml
id: constraint-qr-001
suite: constraint-following
version: 1
input:
  instruction: "只换背景，二维码位置大小不变"
  project_fixture: qr-poster-v1
expected:
  locked_nodes:
    - qr-code
  required_changes:
    - background
metrics:
  - constraint_violation_count
  - required_change_success
  - latency_ms
  - cost_usd
```

所有 dataset 必须版本化；禁止直接改历史 fixture 而不 bump version。

## 4. Runner 类型

### 4.1 Offline deterministic

不调用付费模型，检查：

- schema validity；
- graph routing；
- constraint logic；
- Design IR transforms；
- idempotency；
- API contracts。

### 4.2 Recorded provider replay

通过保存的、脱敏后的 provider response 验证 parsing、routing、fallback 和业务状态变化。

### 4.3 Live provider eval

需要商业 Key，默认 nightly/release 执行，不阻塞普通 PR。必须有预算上限。

### 4.4 Human review

设计主观性强的样本使用 blinded pairwise review；结果进入 dataset metadata。

## 5. Metric Taxonomy

```text
Correctness
├─ schema_valid
├─ task_success
├─ tool_success
├─ constraint_success
└─ identity_success

Quality
├─ visual_score
├─ brand_score
├─ typography_score
└─ human_preference

Reliability
├─ retry_success
├─ resume_success
├─ duplicate_side_effects
└─ provider_failover_success

Efficiency
├─ latency_ms
├─ tokens
├─ provider_cost
└─ total_task_cost
```

任何 suite 必须声明 primary metric 与 guardrail metric。

## 6. Grader 原则

优先级：

1. deterministic grader；
2. programmatic vision/geometry grader；
3. structured model grader；
4. human grader。

能用坐标、schema、hash、OCR 精确判断的问题，禁止只用 LLM judge。

## 7. LangSmith 集成

LangSmith 用于：

- Trace linking；
- dataset/evaluation experiment；
- trajectory/debug；
- prompt/model comparison。

LUMI 自己的 `eval_run_id` 必须可以关联 LangSmith trace/run id，但 LangSmith 不是唯一成绩数据库。核心 benchmark summary 仍需存可导出的 JSON/Parquet/DB 记录。

NODE-05 的 Result/Candidate contract 已预留 `trace_ids`；离线 smoke 不要求 LangSmith credentials，后续 live/agent eval 可附加真实 trace ID。

## 8. Result Schema

```json
{
  "run_id": "...",
  "suite": "planning",
  "suite_version": "1.0",
  "candidate": {
    "agent": "director@0.2.0",
    "prompt": "sha256:...",
    "model_policy": "router@0.1.0"
  },
  "scores": {},
  "cost_usd": 0.0,
  "duration_ms": 0,
  "trace_ids": [],
  "git_sha": "..."
}
```

## 9. Baseline / Candidate

每次 release eval 必须比较：

```text
production baseline
vs
candidate
```

不能只输出 candidate 单次分数。

## 10. Release Gate

最小 gate：

- Primary success rate 不低于 baseline 超过允许阈值。
- Constraint violation 不得恶化。
- Duplicate paid side effect 必须为 0。
- P95 cost 不得无批准显著上涨。
- P95 latency 不能超过 release budget。
- Critical safety/security eval 不得失败。

允许非关键质量项通过 ADR 批准带已知回归发布，但必须记录。

## 11. CLI

```bash
make eval-smoke
make eval SUITE=planning
make eval-live SUITE=image
make eval-report RUN_ID=...
```

CI smoke suite 应在数分钟内完成。

## 12. 测试

Benchmark Harness 自身必须测试：

- invalid case schema 被拒绝；
- grader exception 不被当作 0 分静默吞掉；
- baseline/candidate 配对正确；
- cost 聚合准确；
- report 可复现；
- live run 若没有 Key，明确 SKIPPED 而不是 PASS。

## 13. 验收标准

- [x] dataset schema、runner、grader protocol 可运行。
- [x] 至少 20 个 smoke fixtures。
- [x] offline suite 无付费 Key 可执行。
- [x] report 输出 JSON + Markdown summary。
- [x] candidate 可与 baseline 比较。
- [x] LangSmith trace 可选关联。
- [x] CI 可运行 `eval-smoke`。
- [x] live eval 有明确预算和 skip 机制。

## 14. Definition of Done

```text
eval framework committed                PASS
smoke dataset versioned                 PASS
runner/grader tests green               PASS
baseline comparison works               PASS
CI smoke gate enabled                   PASS
```

下一节点：NODE-06 Lovart Capability Matrix。

## 15. NODE-05 implementation notes

Implemented and accepted through PR `#3`:

- Repository-owned standard-library case/suite/candidate validation and deterministic grader protocol.
- Versioned `smoke@1.0.0` dataset containing 20 cases with task, constraint, and critical-safety scoring.
- Recorded offline baseline and candidate fixtures with per-case cost, latency, and optional trace IDs.
- Stable aggregation including mean/sum/min/max/P95 and deterministic run IDs derived from run content + git SHA.
- Baseline-versus-candidate release gate covering primary success, constraint regression, critical safety, P95 cost, and P95 latency.
- JSON + Markdown report generation under `evals/reports`.
- Explicit live-eval preflight requiring enable flag + API key + positive budget; missing configuration returns `SKIPPED`.
- `make eval-smoke`, `make eval`, `make eval-live`, and `make eval-report` CLI surface.
- 10 harness self-tests cover invalid schema, grader exceptions, pairing, cost aggregation, reproducible reports, live skip semantics, clean gate PASS, and deliberate metric regression FAIL.
- New blocking CI check `eval-smoke` uploads benchmark reports as a 14-day Actions artifact.
- Clean acceptance run `31591585790` passed `frontend`, `python`, `contracts`, `integration`, and `eval-smoke`; Secret Scan `31591585757` also passed.
- Final smoke release gate: task success `1.0 → 1.0`, constraint violations `0 → 0`, critical safety failures `0 → 0`, P95 cost `0.00119 → 0.00109`, P95 latency `119 → 114`.
- Final benchmark artifact: `eval-smoke-reports-31591585790` / `9139339839`.
