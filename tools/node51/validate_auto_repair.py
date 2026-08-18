from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(text: str, *needles: str) -> None:
    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise AssertionError(f"missing required invariants: {missing}")


def forbid(text: str, *needles: str) -> None:
    found = [needle for needle in needles if needle in text]
    if found:
        raise AssertionError(f"forbidden architecture patterns found: {found}")


def main() -> None:
    migration = read("apps/api/migrations/versions/20260818_0020_auto_repair.py")
    require(migration, 'revision = "20260818_0020"', 'down_revision = "20260818_0019"')

    engine = read("services/auto-repair/src/lumi_auto_repair/engine.py")
    require(
        engine,
        "REPAIR_SOURCE_IS_NOT_BRANCH_HEAD",
        "REPAIR_PAID_SIDE_EFFECT_REQUIRES_RECONCILIATION",
        "REPAIR_ACTUAL_COST_EXCEEDED_LOOP_BUDGET",
        "REPAIR_PROMOTION_EXACT_QUALITY_NOT_PASSING",
        "REPAIR_PROMOTION_QUALITY_PROFILE_CHANGED",
        "RepairLoopStatus.STALE_CONFLICT",
        "approve_promoted_version",
    )

    staged = read("apps/api/src/lumi_api/auto_repair/staged_artifact_repository.py")
    require(
        staged,
        "def stage_version",
        "def advance_head_to_staged",
        "staged version must be APPROVED before head promotion",
        "head_version_id IS NOT DISTINCT FROM :expected_head",
    )
    stage_body = staged.split("def stage_version", 1)[1].split(
        "def advance_head_to_staged", 1
    )[0]
    forbid(stage_body, "SET head_version_id")

    artifact = read("apps/api/src/lumi_api/auto_repair/artifact_adapter.py")
    require(
        artifact,
        '"promotion_state": "STAGED_NOT_HEAD"',
        "quality.artifact_version_id != promoted.artifact_version_id",
        "self.service.mark_ready",
        "self.service.approve_version",
        "self.staged_repository.advance_head_to_staged",
    )

    budget = read("apps/api/src/lumi_api/auto_repair/budget_adapter.py")
    require(
        budget,
        "PostgresCostGateway",
        "repair-budget-envelope",
        "delegated-cost-settled-downstream",
        "provider_request_id",
    )
    forbid(budget, "ActualCost(", ".commit(")

    node47_contract = read("services/image-edit/src/lumi_image_edit/contracts_spec.py")
    node47_artifact = read("apps/api/src/lumi_api/image_edit/artifact_adapter.py")
    node47_backend = read("apps/api/src/lumi_api/auto_repair/node47_backend.py")
    require(
        node47_contract,
        "target_branch_id: str | None = None",
        "IMAGE_EDIT_TARGET_BRANCH_INVALID",
    )
    require(
        node47_artifact,
        "IMAGE_EDIT_TARGET_BRANCH_ORG_MISMATCH",
        "IMAGE_EDIT_TARGET_BRANCH_ARTIFACT_MISMATCH",
        "IMAGE_EDIT_TARGET_BRANCH_HEAD_MISMATCH",
    )
    require(
        node47_backend,
        "REPAIR_NODE47_RESULT_ESCAPED_REPAIR_BRANCH",
        "RepairSideEffectUncertain",
        "provider_request_id",
    )

    design_ir = read("apps/api/src/lumi_api/auto_repair/design_ir_backend.py")
    require(
        design_ir,
        "class DesignPreviewRenderPort",
        "REPAIR_STRUCTURAL_NO_SEMANTIC_CHANGE",
        "REPAIR_SET_PROPERTY_NOT_ALLOWLISTED",
        "render_preview",
        "apply_batch",
    )

    persistence = read("apps/api/migrations/versions/20260818_0020_sql/up.sql")
    require(
        persistence,
        "repair_policy_snapshots",
        "auto_repair_jobs",
        "auto_repair_attempts",
        "repair_learning_signals",
        "ck_auto_repair_ready_final",
        "ck_auto_repair_promoted_decision",
        "ck_repair_learning_training_governance",
        "promotion_quality_result_id",
    )

    repo = read("apps/api/src/lumi_api/auto_repair/postgres_repository.py")
    require(
        repo,
        "REPAIR_ATTEMPT_IS_APPEND_ONLY",
        "directive.violation_code",
        "source_violation_ids",
        "REPAIR_TRAINING_REQUIRES_HUMAN_DECISION",
    )

    print("NODE51_AUTO_REPAIR_STATIC_ACCEPTANCE_PASS")


if __name__ == "__main__":
    main()
