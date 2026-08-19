#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    target = ROOT / path
    if not target.is_file():
        raise SystemExit(f"production evidence freezer contract invalid: missing {path}")
    return target.read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"production evidence freezer contract invalid: {message}")


def main() -> int:
    production = read(".github/workflows/freeze-production-evidence.yml")
    recovery = read(".github/workflows/freeze-production-recovery-evidence.yml")

    for token in (
        "Successful Deploy Production workflow run ID",
        "Successful Production Rollback Rehearsal workflow run ID",
        "test \"$(jq -r '.head_sha' <<<\"$run\")\" = \"$RC_SHA\"",
        "test \"$(jq -r '.event' <<<\"$run\")\" = \"workflow_dispatch\"",
        "one /tmp/lumi-rollback-evidence rollback-gate.json \"$EVIDENCE_DIR/rollback/rollback-gate.json\"",
        "--rollback-gate \"$EVIDENCE_DIR/rollback/rollback-gate.json\"",
        "production-rollback-rehearsal-decision.py",
        "production-deployment-decision.py",
        "target_prefix=\"$(dirname \"$MANIFEST_PATH\")/\"",
        "git push origin \"HEAD:${GITHUB_REF_NAME}\"",
    ):
        require(token in production, f"production freezer missing {token!r}")

    for token in (
        "Successful Production DR Rehearsal workflow run ID",
        "test \"$(jq -r '.name' <<<\"$run\")\" = \"Production DR Rehearsal\"",
        "test \"$(jq -r '.head_sha' <<<\"$run\")\" = \"$RC_SHA\"",
        "test \"$(jq -r '.event' <<<\"$run\")\" = \"workflow_dispatch\"",
        "reports' / 'production-recovery' / deployment_id",
        "one baseline-runtime.json",
        "one rds-restore.json",
        "one database-verify.json",
        "one object-recovery.json",
        "one cleanup.json",
        "production-recovery-decision.py",
        "prefix=\"${RECOVERY_DIR}/\"",
        "git push origin \"HEAD:${GITHUB_REF_NAME}\"",
    ):
        require(token in recovery, f"recovery freezer missing {token!r}")

    # The frozen decisions must be recomputed from raw evidence rather than
    # trusting decision.json files delivered by source workflow artifacts.
    require(
        "one decision.json" not in production,
        "production freezer must not trust an artifact-provided decision.json",
    )
    require(
        "one decision.json" not in recovery,
        "recovery freezer must not trust an artifact-provided decision.json",
    )

    print("production evidence freezer contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
