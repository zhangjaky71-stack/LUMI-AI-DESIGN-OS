# NODE-73 Canonical UV Lock Regeneration Failure

- trigger_sha: `75dd0e032663f0e0f5e0a1c2395fd73f5d8b91de`
- failed_stage: `release-action-pins`
- workflow: `regenerate-uv-lock-one-shot.yml`

```text

===== repository-identity =====
PASS: repository-identity

===== release-ref =====
PASS: release-ref

===== exact-trigger-sha =====
PASS: exact-trigger-sha

===== clean-worktree =====
PASS: clean-worktree

===== canonical-regeneration-contract =====
NODE-73 canonical uv-lock two-phase bootstrap contract: PASS
PASS: canonical-regeneration-contract

===== release-action-pins =====
release action pin contract failed: .github/workflows/build-runtime-image-set.yml:99: malformed or unauditable uses line
FAIL(1): release-action-pins

resolver_ok=false
failed_stage=release-action-pins
changed=false
lock_sha256=cef3673d5f5f2c9841db4ca816bef692b9c481884ab81006265c662da9f3c0df
```
