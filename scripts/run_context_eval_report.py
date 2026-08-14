from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from integration_context_eval import CorpusExecutor
from lumi_agent_runtime.context_eval import (
    compare_to_baseline,
    load_baseline,
    load_eval_corpus,
    run_eval_suite,
)
from lumi_agent_runtime.context_eval.reporting import write_report

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run NODE-35 Context evaluation and emit JSON report")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts/context-eval/memory-retrieval-v1.json",
    )
    return parser.parse_args()


async def run(output: Path) -> None:
    suite_id, thresholds, cases = load_eval_corpus(
        ROOT / "evals/context/memory-retrieval-v1.json"
    )
    evaluation = await run_eval_suite(
        suite_id,
        cases,
        executor=CorpusExecutor(),
        thresholds=thresholds,
        verify_determinism=True,
    )
    write_report(output, evaluation)
    if not evaluation.passed:
        failures = {
            result.case_id: result.reasons
            for result in evaluation.report.results
            if not result.passed
        }
        raise AssertionError(f"NODE-35 evaluation failed: {failures}")

    baseline = load_baseline(
        ROOT / "evals/context/memory-retrieval-baseline-v1.json"
    )
    regression = compare_to_baseline(evaluation.report, baseline)
    if not regression.passed:
        raise AssertionError(f"NODE-35 baseline regression: {regression.reasons}")


def main() -> int:
    args = parse_args()
    asyncio.run(run(args.output))
    print(f"NODE-35 context evaluation report written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
