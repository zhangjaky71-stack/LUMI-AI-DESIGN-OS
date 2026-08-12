from __future__ import annotations

import argparse
from pathlib import Path

from .gate import compare_runs
from .live import live_preflight
from .reporting import canonical_json, render_markdown, write_run_report
from .runner import load_json, load_suite, run_suite


EVAL_ROOT = Path(__file__).resolve().parent
DEFAULT_BASELINE = EVAL_ROOT / "fixtures" / "candidates" / "baseline.json"
DEFAULT_CANDIDATE = EVAL_ROOT / "fixtures" / "candidates" / "candidate.json"
DEFAULT_REPORTS = EVAL_ROOT / "reports"


def _run(args: argparse.Namespace) -> int:
    run = run_suite(EVAL_ROOT, args.suite, Path(args.candidate))
    json_path, md_path = write_run_report(Path(args.out), run)
    print(
        canonical_json({"status": "PASS", "json": str(json_path), "markdown": str(md_path)}),
        end="",
    )
    return 0


def _compare(args: argparse.Namespace) -> int:
    suite, _ = load_suite(EVAL_ROOT, args.suite)
    baseline = run_suite(EVAL_ROOT, args.suite, Path(args.baseline))
    candidate = run_suite(EVAL_ROOT, args.suite, Path(args.candidate))
    gate = compare_runs(suite, baseline, candidate)
    baseline_json, _ = write_run_report(Path(args.out), baseline)
    candidate_json, candidate_md = write_run_report(Path(args.out), candidate, gate)
    print(
        canonical_json(
            {
                "status": "PASS" if gate["passed"] else "FAIL",
                "gate": gate,
                "baseline_report": str(baseline_json),
                "candidate_report": str(candidate_json),
                "candidate_markdown": str(candidate_md),
            }
        ),
        end="",
    )
    return 0 if gate["passed"] else 2


def _live(args: argparse.Namespace) -> int:
    result = live_preflight(args.suite)
    print(canonical_json(result), end="")
    return 0


def _report(args: argparse.Namespace) -> int:
    payload = load_json(Path(args.run))
    run = payload.get("run", payload)
    gate = payload.get("gate") if "run" in payload else None
    if not isinstance(run, dict):
        raise ValueError("report input does not contain a run object")
    print(render_markdown(run, gate), end="")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LUMI benchmark harness")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="run one offline deterministic suite")
    run_parser.add_argument("--suite", required=True)
    run_parser.add_argument("--candidate", default=str(DEFAULT_CANDIDATE))
    run_parser.add_argument("--out", default=str(DEFAULT_REPORTS))
    run_parser.set_defaults(func=_run)

    compare_parser = sub.add_parser("compare", help="compare baseline and candidate")
    compare_parser.add_argument("--suite", required=True)
    compare_parser.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    compare_parser.add_argument("--candidate", default=str(DEFAULT_CANDIDATE))
    compare_parser.add_argument("--out", default=str(DEFAULT_REPORTS))
    compare_parser.set_defaults(func=_compare)

    live_parser = sub.add_parser("live", help="perform live-provider preflight")
    live_parser.add_argument("--suite", required=True)
    live_parser.set_defaults(func=_live)

    report_parser = sub.add_parser("report", help="render Markdown from a JSON run report")
    report_parser.add_argument("--run", required=True)
    report_parser.set_defaults(func=_report)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
