# NODE-73 Canonical UV Lock Regeneration Failure

- trigger_sha: `892a47c26e51164fedc4ae7a7c5933109a6b13d6`
- failed_stage: `clean-worktree`
- workflow: `regenerate-uv-lock-one-shot.yml`

```text

===== repository-identity =====
PASS: repository-identity

===== release-ref =====
PASS: release-ref

===== exact-trigger-sha =====
PASS: exact-trigger-sha

===== clean-worktree =====
FAIL(1): clean-worktree

resolver_ok=false
failed_stage=clean-worktree
changed=false
lock_sha256=cef3673d5f5f2c9841db4ca816bef692b9c481884ab81006265c662da9f3c0df
```
