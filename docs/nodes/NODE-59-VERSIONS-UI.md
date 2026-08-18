# NODE-59 — Version History, Compare & Branch UX

> Phase: 7 Frontend Product  
> Status: **CORE IMPLEMENTED / VALIDATING / NOT COMPLETE**  
> Priority: P0  
> Depends on: NODE-42, NODE-55  
> Produces: Version timeline、compare、fork、restore、safe provenance/approval visibility

---

## 0. Implementation snapshot — 2026-08-18

Implemented on `feat/node-59-versions-ui`:

- Product-safe `version-history` projection over NODE-42 Artifact Engine; no new version store or database table.
- History payload contains minimal Artifact identity, branch head/base IDs, version status/hash/quality/creator/time, DesignDocument reference, constraint snapshot and non-sensitive preview metadata.
- Full Artifact file storage locations, full rights records and full provenance are not sent by the history endpoint.
- Safe provenance endpoint exposes only allowlisted traceability/model/hash/source/recipe/code/compiler fields and excludes raw prompts, prompt refs, provider request IDs and private reasoning/tool payloads.
- Browser adds an independent private-provenance-key rejection fence.
- Product user Fork/Restore endpoints derive creator identity from the authenticated actor; clients cannot claim creator type/id.
- Product Restore derives minimal server-side provenance referencing the exact source version; browser does not fabricate canonical provenance.
- Restore preserves Artifact Engine branch-head compare-and-swap through `expected_head_version_id` and returns a new version summary.
- Workspace Inspector now contains an exact Version History panel for the selected Artifact.
- Version timeline displays version number, branch, HEAD, approval/status, creator, time and quality.
- Structured change summary is computed on demand from NODE-38 semantic diff categories; no LLM-authored version summary.
- Compare locks two exact ArtifactVersion IDs and supports Design semantic changes or finite raster metrics without stringifying arbitrary compare metadata.
- Fork from the currently viewed exact version is available.
- Restore clearly states that it creates a new version and does not delete later history; stale branch-head conflict forces refresh/review.
- Safe provenance panel shows traceability, provider/model, agent/recipe, prompt hash/template, source counts, constraint snapshot, code and compiler identity.
- Background history polling can announce a new branch head without changing the exact Canvas version or current compare pair.
- Approved versions remain immutable canonical records; status badge is read directly from ArtifactVersion.

NODE-59 remains **NOT COMPLETE** because visual side-by-side/wipe/heatmap requires a canonical preview renderer, NODE-38 does not yet expose before/after property values, approval audit details and exact BrandRuleSet provenance are not projected, large-history pagination/virtualization is not closed, and browser/PostgreSQL E2E plus hosted executed-green CI are still missing.

## 1. 目标

把 Artifact Engine 的不可变历史变成用户能理解的版本体验。用户可以安全尝试 AI/手工修改，并从任意历史版本比较、分支或恢复，而不是修改旧记录。

## 2. Version Panel

每项显示：

```text
version number
branch / HEAD
status / APPROVED badge
creator: user / agent / system / import
time
quality score
structured changes on demand
```

Preview URL 不得从 storage key 拼接；没有 canonical preview renderer 时只显示安全 preview metadata。

## 3. Semantic Summary

Design IR summary只来自 NODE-38：

```text
nodes_added
nodes_removed
properties_changed
text_changed
geometry_changed
asset_replaced
constraints_changed
```

禁止让 LLM 自由生成“看起来合理”的改动说明。当前 semantic diff 不携带 before/after 属性值，因此诸如 `68 → 58` 仍是 gap。

## 4. Compare

Compare始终绑定两个 exact ArtifactVersion IDs。

### Design IR

- structured semantic change categories；
- changed node/property references；
- exact left/right open actions。

### Raster

- finite visual metrics when Artifact Engine provides them；
- canonical preview renderer完成前，不伪造side-by-side/wipe/heatmap。

## 5. Restore

UI明确显示：

> Restore creates a new version on the selected branch. It never deletes later history.

产品 API 不接受 client provenance/creator。服务端派生 restore provenance，并把 target branch 当前 head 作为 CAS fence。409 时刷新，不盲重试。

## 6. Fork

从任意当前查看版本创建新 branch。Fork 不修改源版本，不创建假 merge。

## 7. Approval

ArtifactVersion `APPROVED` 是 canonical badge。继续编辑/restore 都创建新版本，旧 APPROVED version 保留不变。完整 approval audit projection 尚未闭合。

## 8. Provenance Panel

公开：

```text
traceability score/status
provider / model
agent / recipe
prompt hash / template version
source asset count
source artifact version count
constraint snapshot hash
skill versions
code git sha
compiler version
```

不公开：

```text
raw prompt
prompt_ref
provider_request_id
messages
system prompt
reasoning / scratchpad
raw tool output
secrets / authorization
```

BrandRuleSet exact version 尚未包含在 ArtifactVersion public contract，保持 gap。

## 9. Concurrency

History 首次加载时保存 branch head snapshot。后台 refresh 发现 head 变化只显示更新提示；不得自动改变 Canvas 当前 exact version，也不得改变正在比较的两个 exact IDs。

## 10. Tests

Core test surface覆盖：

- history projection不泄露storage/provenance；
- safe provenance allowlist；
- user mutation request不能提交creator/provenance；
- restore route使用head fence和server-derived provenance；
- structured semantic diff projection；
- browser private provenance rejection；
- concurrent new-head detection；
- existing NODE-42 restore creates new / approved terminal behavior继续作为底层证据。

## 11. 验收标准

- [x] 用户能浏览 canonical version/branch history core。
- [x] Compare 使用 exact version IDs。
- [x] Semantic summary 来自 structured diff，不由 LLM 编造。
- [x] Restore 创建新版本并保留历史，且有 stale-head fence。
- [x] Fork 使用 exact source version。
- [x] APPROVED status 可见且旧版本不被 rewrite。
- [x] Safe provenance 不暴露 raw prompt/private reasoning/provider request ref。
- [x] Concurrent head update 不自动切换当前 version/compare。
- [ ] Canonical visual side-by-side/wipe/heatmap。
- [ ] Before/after exact property values。
- [ ] Approval audit detail / permission projection。
- [ ] BrandRuleSet exact version provenance。
- [ ] Large-history pagination/virtualization。
- [ ] Browser/PostgreSQL E2E + Hosted executed green CI。

## 12. Definition of Done

```text
version history/compare/fork/restore E2E green
+ safe provenance permissions green
+ canonical visual compare green
+ hosted CI executed green
```

当前未满足完整 Definition of Done，因此保持 **NOT COMPLETE**。

下一节点：NODE-60 Export UI。
