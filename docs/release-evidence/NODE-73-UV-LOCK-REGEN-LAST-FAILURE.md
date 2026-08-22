# NODE-73 Canonical UV Lock Regeneration Failure

- trigger_sha: `2e8074ce9e4dfe796576356374f61835ef8e86f1`
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
release action pin contract failed: action docker/setup-buildx-action@v4.2.0 must use a full lowercase SHA40
FAIL(1): release-action-pins

resolver_ok=false
failed_stage=release-action-pins
changed=false
lock_sha256=cef3673d5f5f2c9841db4ca816bef692b9c481884ab81006265c662da9f3c0df
```
