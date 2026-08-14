from __future__ import annotations

import ast
import json
from pathlib import Path

from lumi_agent_runtime.context_eval import EvalCategory, load_baseline, load_eval_corpus

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "apps/agent-runtime/src/lumi_agent_runtime/context_eval"
CORPUS = ROOT / "evals/context/memory-retrieval-v1.json"
BASELINE = ROOT / "evals/context/memory-retrieval-baseline-v1.json"
REQUIRED = {
    "__init__.py",
    "baseline.py",
    "contracts.py",
    "evaluator.py",
    "loader.py",
    "reporting.py",
    "runner.py",
    "suite.py",
}
FORBIDDEN_IMPORTS = {
    "asyncpg",
    "sqlalchemy",
    "psycopg",
    "requests",
    "subprocess",
    "docker",
    "openai",
    "anthropic",
    "google",
}


def require(path: str, *markers: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    for marker in markers:
        if marker not in text:
            raise SystemExit(f"{path}: missing NODE-35 marker: {marker}")
    return text


def main() -> int:
    missing = sorted(name for name in REQUIRED if not (PACKAGE / name).is_file())
    if missing:
        raise SystemExit(f"NODE-35 eval modules missing: {missing}")
    suite_id, thresholds, cases = load_eval_corpus(CORPUS)
    if suite_id != "memory-retrieval-v1":
        raise SystemExit("NODE-35 canonical suite ID drifted")
    if len(cases) != 8 or {case.category for case in cases} != set(EvalCategory):
        raise SystemExit("NODE-35 canonical corpus must cover all eight categories exactly once")
    if thresholds.min_case_pass_rate != 1.0:
        raise SystemExit("NODE-35 P0 case pass rate must be 1.0")
    if any(
        value != 0
        for value in (
            thresholds.max_forbidden_source_leaks,
            thresholds.max_forbidden_phrase_leaks,
            thresholds.max_token_budget_violations,
            thresholds.max_injection_authority_violations,
            thresholds.max_freshness_violations,
        )
    ):
        raise SystemExit("NODE-35 security/budget/freshness violation budget must be zero")
    baseline = load_baseline(BASELINE)
    if baseline.suite_id != suite_id:
        raise SystemExit("NODE-35 baseline suite mismatch")

    require(
        "apps/agent-runtime/src/lumi_agent_runtime/context_eval/evaluator.py",
        "source_recall",
        "fact_recall",
        "forbidden_source_leaks",
        "provenance_coverage",
        "token_budget_violations",
        "injection_authority_violations",
        "freshness_violations",
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/context_eval/runner.py",
        "verify_determinism",
        "manifest_hash_equal",
        "rendered_hash_equal",
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/context_eval/baseline.py",
        "SOURCE_RECALL_REGRESSION",
        "FACT_RECALL_REGRESSION",
        "PROVENANCE_REGRESSION",
        "CASE_PASS_RATE_REGRESSION",
    )
    require(
        "apps/agent-runtime/src/lumi_agent_runtime/context_eval/reporting.py",
        '"lumi.context-eval-report.v1"',
        '"aggregate"',
        '"determinism"',
    )
    require(
        "scripts/run_context_eval_report.py",
        "write_report",
        "compare_to_baseline",
        "artifacts/context-eval/memory-retrieval-v1.json",
    )
    long_eval = require(
        "scripts/integration_context_eval.py",
        "required-source-recall",
        "CorpusExecutor",
        "verify_determinism=True",
        "forbidden_source_leaks == 0",
        "injection_authority_violations == 0",
    )
    if "uuid4(" in long_eval:
        raise SystemExit("NODE-35 deterministic benchmark must not generate random IDs")
    require(
        "scripts/integration_context_eval_baseline.py",
        "compare_to_baseline",
        "memory-retrieval-baseline-v1.json",
    )

    corpus_raw = json.loads(CORPUS.read_text(encoding="utf-8"))
    expected_case_ids = {
        "required-source-recall",
        "compressed-fact-retention",
        "cross-project-isolation",
        "prompt-injection-containment",
        "hard-token-budget",
        "latest-summary-freshness",
        "distractor-resilience",
        "provenance-completeness",
    }
    if {row["case_id"] for row in corpus_raw["cases"]} != expected_case_ids:
        raise SystemExit("NODE-35 canonical case IDs drifted")

    for path in PACKAGE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".", 1)[0] for alias in node.names}
                if roots & FORBIDDEN_IMPORTS:
                    raise SystemExit(f"Context eval imports ambient authority: {path}")
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".", 1)[0] in FORBIDDEN_IMPORTS:
                    raise SystemExit(f"Context eval imports ambient authority: {path}")

    print("NODE-35 Memory/Retrieval evaluation contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
