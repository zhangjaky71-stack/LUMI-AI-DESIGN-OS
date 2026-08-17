# NODE-48 — Video Generation & Composition

> Phase: 6 Generation & Quality  
> Status: **IMPLEMENTED / VALIDATING / not COMPLETE**  
> Priority: P1 product parity, P0 architecture-ready  
> Depends on: NODE-19, NODE-22, NODE-27, NODE-42, NODE-43, NODE-44, NODE-46  
> Produces: Storyboard/Shot/Keyframe, async provider jobs, verified Video Clips, typed timeline, final Video Artifact

---

## 1. 目标

把视频生成做成长任务生产链，而不是让 Agent/LangGraph 同步等待 provider。支持 text-to-video、image-to-video、keyframe/product-motion/loop 和 shot-based campaign video，并通过媒体 worker 完成安全组合与最终 Artifact 落地。

正式运行时 provider submit 必须进入 `PENDING`，之后由 NODE-19 scheduler/webhook 唤醒 bounded `resume()`；一次 resume 对每个等待中的 Shot 最多 poll 一次。

## 2. Domain

```text
VideoTaskSpec
Storyboard
ShotSpec
CompiledShot
ShotRuntime
ProviderJobRecord
StoredVideoClip
VideoTimeline
RenderedVideo
VideoJob
FinalVideoProvenance
```

Video Artifact 仍使用统一 NODE-42 Artifact Engine；NODE-48 不另建平行版本系统。

## 3. Storyboard

Video Agent 输出结构化：

```text
objective / mode
duration target
aspect ratio / width / height / fps
shots[]
  shot id
  duration
  visual prompt
  camera motion
  source/reference assets
  identity refs
  transition
brand rule snapshot
agent / recipe / skill / git provenance
```

每个 Shot 都有确定性的 paid operation id：

```text
root operation id + shot id + retry ordinal
```

初次调用可安全重放；显式重试生成新的 operation id。

## 4. Shot Generation

每个 Shot 是独立 provider side effect。失败只重试该 Shot，不重新生成已经 READY 的 Shot。

当前模式：

```text
TEXT_TO_VIDEO
IMAGE_TO_VIDEO
KEYFRAME_TO_VIDEO
PRODUCT_MOTION
LOOP
```

这些高层模式最终编译到 NODE-22：

```text
video.text_to_video
video.image_to_video
```

## 5. Provider Feature Registry

视频 provider 的额外能力通过版本化 `VideoFeatureRegistry` 约束：

```text
video.start_frame
video.reference_image
video.camera_controls
```

需要这些能力时若没有 registry snapshot，调用在付费 side effect 前 fail closed。缺少所需能力的 provider 会从当前 NODE-22 route 中排除。

## 6. Async Lifecycle

```text
PLANNED
→ Model Gateway estimate
→ submit each Shot
→ PENDING + provider_request_id
→ WAITING_EXTERNAL
→ scheduler/webhook
→ resume()
→ poll once
→ staging fetch
→ probe + SHA-256
→ Identity / Brand / safety validation
→ clip READY
→ all READY
→ COMPOSING
→ typed FFmpeg sandbox
→ final Artifact
→ COMPLETED
```

provider 异步等待不占 Agent Graph worker。

## 7. Validation

每个 clip：

- container/MIME allowlist；
- resolution；
- duration tolerance；
- decodable frames；
- black-frame ratio；
- provider safety hard reject；
- Identity Engine（存在 identity refs 时强制）；
- Brand Rules（存在 brand snapshot 时强制）。

Identity/Brand validator 缺失时 fail closed，不把未验证的 clip 标为 READY。

## 8. Output Boundary

Provider URL/ref 只能作为临时输入：

```text
provider output
→ fetch_to_staging
→ size/MIME check
→ media probe
→ SHA-256
→ internal durable storage
→ StoredVideoClip
```

外部 URL 不进入 durable Artifact truth。

## 9. Timeline

P0 timeline schema：

```text
ordered video clips
clip start/duration
CUT / FADE
reserved audio ref
reserved subtitle ref
width / height / fps
```

不做 Premiere replacement；复杂 NLE 属于后续能力。

## 10. FFmpeg Worker

所有 composition/render 必须在 media sandbox/worker：

- typed argv only；
- `shell=False`；
- 禁止 network/protocol input；
- 禁止 relative/traversal path；
- 不接受用户提供的任意 filter string；
- CPU / memory / timeout / output size 明确受限。

P0 组合支持 deterministic concat 与 bounded fade。

## 11. Cost

开始前计算 Shot estimate 总和；超出任务预算则不 submit。每个 Shot 同时收到独立 request budget cap。

NODE-27 / Model Gateway 是真实货币结算唯一 owner。NODE-48 的 `video_generation_cost_projection` 仅用于审计投影，数据库约束固定：

```text
monetary_owner = NODE27_MODEL_GATEWAY_SETTLEMENT
```

## 12. Cancellation

provider 支持 cancel：调用 NODE-22 cancel；不支持/未确认取消则进入 `CANCEL_REQUESTED`。

取消后 provider 若迟到返回 COMPLETED，NODE-48 直接 discard，不再 materialize 成用户可见 Artifact。

## 13. Provenance

Final provenance 记录：

- task semantic hash；
- Shot id / paid operation id / retry ordinal；
- source Asset + rights snapshot；
- provider/model/provider request id；
- identity refs；
- cost projection；
- renderer version；
- Brand snapshot；
- AgentRun / agent / recipe / skills / git commit。

不持久化 provider secrets、signed URL、隐藏系统 prompt 或 raw provider payload。

## 14. Persistence

Alembic revision：`20260817_0017`，直接接在 NODE-47 `20260817_0016` 后。

表：

```text
video_generation_specs
video_generation_jobs
video_generation_shots
video_provider_jobs
video_generation_clips
video_generation_cost_projection
video_webhook_dedupe
```

## 15. Tests & Gates

已提交自动化测试/门禁覆盖：

- async mock provider；
- deterministic operation id；
- partial shot retry；
- operation id conflict；
- webhook duplicate；
- cancel + late result discard；
- Identity/Brand fail closed；
- black frame / provider safety rejection；
- FFmpeg protocol/shell injection boundary；
- final provenance；
- PostgreSQL migration；
- 2,000-shot deterministic planning benchmark。

Dedicated CI：

```text
video-contract
video-quality
video-db
video-benchmark
```

## 16. 验收标准

- [x] Storyboard → Shots → Final Video control plane 已实现。
- [x] provider 异步通过 `PENDING / WAITING_EXTERNAL / resume`，不在 Graph 内长轮询。
- [x] 单 Shot 显式重试，不重生成 READY Shot。
- [x] FFmpeg typed argv + mandatory sandbox contract。
- [x] Shot 级预算与 cost projection，NODE-27 保持货币 truth owner。
- [x] video source / rights / provider / agent / renderer provenance 完整建模。
- [ ] Hosted NODE-48 workflow 实际执行 green。
- [ ] 选定 live provider/model 的真实视频质量与取消/成本验收 green。
- [ ] Production worker/storage/Artifact/Identity/Brand adapters 全部接线并跑真实基础设施验收。

## 17. Definition of Done

当前结论：**IMPLEMENTED / VALIDATING / not COMPLETE**。

只有满足以下全部条件才能标记 COMPLETE：

```text
control-plane tests green
+ hosted PostgreSQL/quality/benchmark gates green
+ NODE-19 durable worker/webhook recovery green
+ NODE-42 Artifact production bridge green
+ NODE-43/NODE-44 multi-frame validation calibration green
+ selected live provider/model acceptance green
```

运行架构：`docs/runtime/VIDEO-GENERATION-V1.md`  
验收记录：`reports/nodes/NODE-48/acceptance.md`  
生产差距：`reports/nodes/NODE-48/gap-ledger.json`

下一节点：**NODE-49 — Export Engine**。
