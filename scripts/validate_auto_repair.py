from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "packages/auto-repair-engine/package.json",
    "packages/auto-repair-engine/src/types.ts",
    "packages/auto-repair-engine/src/ports.ts",
    "packages/auto-repair-engine/src/planner.ts",
    "packages/auto-repair-engine/src/structural.ts",
    "packages/auto-repair-engine/src/comparator.ts",
    "packages/auto-repair-engine/src/runtime.ts",
    "packages/auto-repair-engine/src/memory-repository.ts",
    "packages/auto-repair-engine/src/auto-repair.test.ts",
    "packages/auto-repair-engine/src/money.test.ts",
    "packages/auto-repair-engine/src/repair-benchmark.test.ts",
    "db/migrations/0010_auto_repair.sql",
    "evals/datasets/auto-repair/suite.json",
    "evals/datasets/auto-repair/v1/cases.json",
    "evals/fixtures/auto-repair/baseline.json",
    "evals/fixtures/auto-repair/candidate.json",
    "docs/nodes/NODE-51-AUTO-REPAIR.md",
    "docs/runtime/AUTO-REPAIR-V1.md",
    "reports/nodes/NODE-51/acceptance.md",
    ".github/workflows/auto-repair.yml",
]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    for path in REQUIRED:
        require((ROOT / path).is_file(), f"missing NODE-51 file: {path}")

    runtime = read("packages/auto-repair-engine/src/runtime.ts")
    planner = read("packages/auto-repair-engine/src/planner.ts")
    structural = read("packages/auto-repair-engine/src/structural.ts")
    comparator = read("packages/auto-repair-engine/src/comparator.ts")
    ports = read("packages/auto-repair-engine/src/ports.ts")
    money = read("packages/auto-repair-engine/src/money.ts")
    migration = read("db/migrations/0010_auto_repair.sql")
    workflow = read(".github/workflows/auto-repair.yml")
    tests = read("packages/auto-repair-engine/src/auto-repair.test.ts")

    require("max_auto_repair_iterations" in runtime and "<= this.#options.policy.max_auto_repair_iterations" in runtime, "bounded iteration loop missing")
    require("attempted_fingerprints" in planner and "attempted_fingerprints" in runtime, "repeat-repair guard missing")
    require('kind: "STRUCTURAL_DESIGN_OP"' in planner and 'estimated_cost_usd: "0"' in planner, "zero-cost structural priority missing")
    require("guardedExecute" in structural and "AUTO_REPAIR_CONSTRAINT_PREFLIGHT_DENIED" in structural, "NODE-39 guarded structural execution missing")
    require("NEW_HARD_VIOLATION" in comparator and "QUALITY_REGRESSION" in comparator, "quality rollback gates missing")
    require("persistCandidate" in runtime and "quality.evaluate" in runtime and "promoteCandidate" in runtime, "candidate lifecycle missing")
    require(runtime.index("persistCandidate") < runtime.index("quality.evaluate") < runtime.index("promoteCandidate"), "candidate must persist off-head before quality and promote after quality")
    require("budget.reserve" in runtime and "#executeGenerative" in runtime, "paid reservation/generative boundary missing")
    require(runtime.index("budget.reserve") < runtime.index("#executeGenerative", runtime.index("budget.reserve")), "paid repair must reserve before execution")
    require("AUTO_REPAIR_PAID_REPAIR_WITHOUT_RESERVATION" in runtime, "paid repair fail-closed guard missing")
    require("parseUsdMicros" in money and "BigInt" in money, "integer decimal cost accounting missing")
    require("BudgetReservationPort" in ports and "GenerativeRepairPort" in ports, "spec-only NODE-27/NODE-47 adapter boundaries missing")
    require("simulateExternalHead" in tests and "STALE_SOURCE" in tests, "concurrent edit stale test missing")
    require("NEW_HARD_VIOLATION" in comparator and "QR_PAYLOAD_CHANGED" in tests, "new hard violation rollback test missing")

    provider_markers = ["openai", "anthropic", "@google/generative-ai", "replicate", "fal-ai"]
    package_text = "\n".join(read(str(path.relative_to(ROOT))) for path in (ROOT / "packages/auto-repair-engine/src").glob("*.ts"))
    lower = package_text.lower()
    for marker in provider_markers:
        require(marker not in lower, f"provider SDK leakage into Auto Repair Engine: {marker}")

    for table in ["auto_repair_policies", "auto_repair_loops", "auto_repair_attempts"]:
        require(f"CREATE TABLE IF NOT EXISTS {table}" in migration, f"missing DB table {table}")
    require("promote_auto_repair_candidate" in migration, "transactional candidate promotion function missing")
    require("head_version_id IS NOT DISTINCT FROM p_expected_branch_head" in migration, "branch CAS predicate missing")
    require("AUTO_REPAIR_BRANCH_HEAD_CAS_CONFLICT" in migration, "CAS conflict error missing")
    require("status = 'DRAFT'" in migration and "DO NOT mutate artifact_branches" in migration, "off-head DRAFT persistence contract missing")
    require("second financial ledger" in migration, "NODE-27 ownership warning missing")

    suite = json.loads(read("evals/datasets/auto-repair/suite.json"))
    cases = json.loads(read("evals/datasets/auto-repair/v1/cases.json"))["cases"]
    require(suite["name"] == "auto-repair", "NODE-05 suite name mismatch")
    require(len(cases) >= 8, "Auto Repair release-gate suite needs at least 8 cases")

    for job in ["repair-contract", "repair-quality", "repair-integration", "repair-budget", "repair-db", "repair-benchmark"]:
        require(f"{job}:" in workflow, f"missing CI job {job}")

    print("NODE-51 Auto Repair architecture validation: PASS")


if __name__ == "__main__":
    main()
