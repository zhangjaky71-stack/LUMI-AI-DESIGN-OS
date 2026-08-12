# NODE-48 — Video Generation & Composition

> Phase: 6 Generation & Quality  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P1 product parity, P0 architecture-ready  
> Depends on: NODE-19, NODE-22, NODE-27, NODE-42, NODE-46  
> Produces: Storyboard/Shot/Keyframe/Video Provider异步任务、FFmpeg组合与Video Artifact

---

## 1. 目标

把视频生成做成长任务生产链，而不是 Agent同步等 provider。支持 text-to-video、image-to-video、shot-based campaign video，并通过媒体 worker完成拼接、音频、字幕和导出。

## 2. Domain

```text
VideoProjectPlan
Storyboard
Shot
Keyframe
VideoGenerationJob
VideoClip
Timeline
RenderJob
```

Video Artifact仍使用统一 Artifact Engine。

## 3. Storyboard

Video Agent输出结构化：

```text
objective
duration target
aspect ratio
shots[]
  shot id
  duration
  visual prompt
  camera
  source/reference assets
  dialogue/copy
  transition
identity refs
brand rules
```

## 4. Shot Generation

每 shot独立Task，可并行但受 budget/concurrency。失败可只重试某shot，不重生成全片。

## 5. Modes

```text
TEXT_TO_VIDEO
IMAGE_TO_VIDEO
KEYFRAME_TO_VIDEO
PRODUCT_MOTION
LOOP
```

Capability Registry选择 provider。

## 6. Async Lifecycle

```text
Task
→ SideEffect submit
→ provider id
→ WAITING_EXTERNAL
→ poll/webhook
→ download/validate
→ clip READY
→ TaskGraph resume
```

长poll由worker/scheduler，不占 LangGraph线程。

## 7. Validation

每clip：

- container/codec解析；
- duration；
- resolution；
- frames可decode；
- audio metadata；
- content/identity quality profile；
- no empty/black frame thresholds。

## 8. Identity

商品/Logo hard identity可在关键帧/采样帧检测。Character consistency P1用多帧抽样与reference set。

## 9. Timeline

P0 timeline schema：

```text
video tracks
clip start/end
trim
simple transition
audio track
subtitle/caption track
```

不做完整 Premiere replacement。

## 10. FFmpeg Worker

所有 composition/render在 media sandbox/worker：

- concat；
- trim；
- scale/crop；
- simple transitions；
- audio mix；
- subtitle burn-in/sidecar；
- thumbnail/contact sheet。

参数由 typed render spec生成，不拼接未经校验的 shell command。

## 11. Audio

P1可接 voice/music providers；rights/voice consent单独治理。P0允许用户上传/许可音频 + 简单配乐接口，不默认生成仿冒特定真人声音。

## 12. Cost

shot级估算/reserve/actual；生成失败、延长、upscale都入 ledger。用户界面显示视频成本较高的明确估算。

## 13. Cancellation

provider支持 cancel则调用；不支持则标 CANCEL_REQUESTED，结果到达后按policy discard/archive并记录可能成本。

## 14. Provenance

每 clip和final video记录 source assets、shot spec、provider/model、seed/options、render spec、FFmpeg版本、music/source rights。

## 15. Tests

- async mock provider；
- partial shot retry；
- webhook duplicate；
- cancel；
- corrupted clip；
- FFmpeg render spec injection；
- identity sample；
- final provenance。

## 16. 验收标准

- [ ] Storyboard→Shots→Final Artifact可跑通。
- [ ] provider异步不占Graph worker。
- [ ] 单shot可重试。
- [ ] FFmpeg typed render。
- [ ] 成本按shot追踪。
- [ ] video source/rights/provenance完整。

## 17. Definition of Done

```text
video task pipeline implemented
+ mock E2E green
+ selected live provider acceptance green
+ render/cancel/retry tests green
```

下一节点：NODE-49 Export Engine。
