from __future__ import annotations

import asyncio
from pathlib import Path

from integration_context_eval import CorpusExecutor
from lumi_agent_runtime.context_eval.baseline import compare_to_baseline, load_baseline
from lumi_agent_runtime.context_eval.loader import load_eval_corpus
from lumi_agent_runtime.context_eval.runner import run_eval_suite

ROOT = Path(__file__).resolve().parents[1]


async def main_async() -> None:
    suite_id, thresholds, cases = load_eval_corpus(
        ROOT / "evals/context/memory-retrieval-v1.json"
    )
    run = await run_eval_suite(
        suite_id,
        cases,
        executor=CorpusExecutor(),
        thresholds=thresholds,
        verify_determinism=True,
    )
    if not run.passed:
        raise AssertionError("NODE-35 suite failed before baseline comparison")
    baseline = load_baseline(
        ROOT / "evals/context/memory-retrieval-baseline-v1.json"
    )
    regression = compare_to_baseline(run.report, baseline)
    if not regression.passed:
        raise AssertionError(f"NODE-35 baseline regression: {regression.reasons}")


def main() -> int:
    asyncio.run(main_async())
    print("NODE-35 approved-baseline regression: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
