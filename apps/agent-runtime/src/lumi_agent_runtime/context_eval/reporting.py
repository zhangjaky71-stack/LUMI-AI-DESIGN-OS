from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .runner import ContextEvalRun


def report_payload(run: ContextEvalRun) -> dict[str, object]:
    return {
        "schema": "lumi.context-eval-report.v1",
        "suite_id": run.report.suite_id,
        "passed": run.passed,
        "pass_rate": run.report.pass_rate,
        "aggregate": asdict(run.report.aggregate),
        "thresholds": asdict(run.report.thresholds),
        "results": [
            {
                "case_id": result.case_id,
                "passed": result.passed,
                "metrics": asdict(result.metrics),
                "reasons": list(result.reasons),
                "manifest_hash": result.manifest_hash,
                "rendered_hash": result.rendered_hash,
            }
            for result in run.report.results
        ],
        "determinism": [
            {
                "case_id": item.case_id,
                "passed": item.passed,
                "manifest_hash_equal": item.manifest_hash_equal,
                "rendered_hash_equal": item.rendered_hash_equal,
            }
            for item in run.determinism
        ],
    }


def write_report(path: Path, run: ContextEvalRun) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report_payload(run), ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
