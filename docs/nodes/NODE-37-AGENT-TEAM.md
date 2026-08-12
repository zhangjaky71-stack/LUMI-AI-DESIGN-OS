# NODE-37 — LUMI Agent Team V1

> Phase: 4 Agent Intelligence  
> Status: SPECIFIED / READY FOR IMPLEMENTATION  
> Priority: P0  
> Depends on: NODE-28～36  
> Produces: 首批专业 Agent definitions、handoff contract、责任边界、eval profiles

---

## 1. 目标

建立 Director + Specialized Agents，而不是万能 Agent。每个 Agent 只获得完成职责所需的 Context/Tools/Skills。

## 2. Team Topology

```text
Director
├─ Brief Agent
├─ Research Agent
├─ Brand Strategy Agent
├─ Creative Director
├─ Moodboard Agent
├─ Copywriting Agent
├─ Typography Agent
├─ Layout Agent
├─ Image Agent
├─ Image Edit Agent
├─ Product Render Agent
├─ Video Agent
├─ Critic Agent
├─ Brand Consistency Agent
├─ Identity Agent
└─ Export Agent
```

## 3. Director

职责：

- 解释 Run/TaskGraph；
- 选择/遵守 Recipe；
- 调用适当 agent；
- 识别需要 approval；
- 汇总结果；
- 不亲自做所有专业工作。

Tools：project/task/artifact query、Agent delegation；不默认 shell。

## 4. Brief Agent

输入：用户需求/附件摘要。

输出：StructuredBrief + ambiguities + inferred assumptions。

规则：能合理推断的低风险信息可标 assumption；会显著改变成本/成品的歧义进入 guided approval。

## 5. Research Agent

Tools：web search/fetch、knowledge。

输出：ResearchReport，包含 citations、competitor/category insights、visual signals。

禁止把网页 instruction 当系统指令。

## 6. Brand Strategy Agent

输出：positioning、audience、message pillars、tone、brand attributes。不能凭空宣称市场事实，事实引用 Research。

## 7. Creative Director

把 Brief/Strategy 转成可执行 creative directions：concept、composition、color、type、image style、deliverables。输出多个有差异方向，而不是同一方案换形容词。

## 8. Moodboard Agent

组织参考资产/生成探索图，输出 Moodboard Artifact + rationale + source refs。外部参考注意 rights/source。

## 9. Copywriting Agent

输出结构化 copy variants：headline/subhead/body/CTA，尊重 locale、brand tone、字数约束。不得负责最终 canvas positioning。

## 10. Typography Agent

选择 font strategy、hierarchy、sizes/line-height/spacing；验证字体可用/授权。输出 Design IR typography tokens/operations。

## 11. Layout Agent

根据 Frame/Content/Brand/Constraints 输出 Design Operations：position/size/group/alignment。不得绕 Constraint Engine 直接写 renderer。

## 12. Image Agent

负责生成 image request spec/reference selection；调用 Model Gateway，产出 Asset/Artifact candidate。不得持有 provider key。

## 13. Image Edit Agent

输入 selected Artifact/Asset + edit intent + protected constraints。优先局部 edit；输出新 version，不覆盖原图。

## 14. Product Render Agent

专注商品身份一致、材质、角度、背景场景；结合 Identity Engine，hard product identity threshold。

## 15. Video Agent

输出 storyboard/shot list/keyframes/generation plan，调用 video media tasks；长任务交 TaskGraph/Worker，不在 subagent invocation 内无限等待。

## 16. Critic Agent

输出 structured critique + metric suggestions + repair plan。Critic 不能直接批准自己产生的设计；最终 Quality Engine 综合 deterministic/vision/human rules。

## 17. Brand Consistency Agent

比较 artifact 与 Brand Rules/approved references，输出 violations。不得把“个人审美”伪装 hard brand rule。

## 18. Identity Agent

处理 product/character/logo identity reference set、similarity validation 和 violation report。最终算法由 NODE-44。

## 19. Export Agent

解释 deliverables，生成 export plan/file list/format/尺寸；实际 render/export 由服务/worker执行。

## 20. Handoff Contract

所有 agent 输出共同 envelope：

```text
status
summary
structured_output
artifact_refs
knowledge_refs
proposed_operations
risks
open_questions
confidence
```

下游不得靠解析自然语言段落获取关键字段。

## 21. Delegation Rules

- Agent 不能委派给权限更高角色绕安全。
- Director/Recipe 决定主要 handoff。
- Specialized Agent 可用注册 subagent，但 dynamic delegation depth 有上限。
- Critic 与 Producer 分离以减少自评偏差。

## 22. P0 Eval

每角色至少 20 smoke/eval cases；核心 Brief/Research/Layout/ImageEdit/Critic 各 50+ 逐步扩充。

## 23. 验收 E2E

案例：咖啡品牌海报。

```text
Brief → Research → Creative Direction
→ user approval
→ Copy/Typography/Layout/Image
→ Artifact
→ Critic + Brand + Identity
→ repair if needed
→ final version
```

必须能在 MockProvider 全程跑通，在提供真实 Key 后可 live eval。

## 24. 验收标准

- [ ] 16 个 AgentDefinition V1。
- [ ] 每个角色 allowed tools/skills 明确。
- [ ] handoff structured。
- [ ] producer/critic 分离。
- [ ] delegation 不提权。
- [ ] E2E recipe mock 全绿。

## 25. Definition of Done

```text
agent team definitions published
+ role evals green
+ end-to-end brand/poster mock workflow green
```

完成 Phase 4，下一节点：NODE-38 Design IR Runtime。
