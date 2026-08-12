from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def render_markdown(run: dict[str, Any], gate: dict[str, Any] | None = None) -> str:
    lines = [
        f"# LUMI Eval Report — {run['suite']}@{run['suite_version']}",
        "",
        f"- Run ID: `{run['run_id']}`",
        f"- Candidate: `{run['candidate']['name']}@{run['candidate']['version']}`",
        f"- Git SHA: `{run['git_sha']}`",
        f"- Primary metric: `{run['primary_metric']}`",
        "",
        "## Scores",
        "",
        "| Metric | Score |",
        "|---|---:|",
    ]
    for metric, score in sorted(run["scores"].items()):
        lines.append(f"| `{metric}` | {score:.6f} |")
    if gate is not None:
        lines.extend(
            [
                "",
                "## Release Gate",
                "",
                f"**{'PASS' if gate['passed'] else 'FAIL'}**",
                "",
                "| Metric | Baseline | Candidate | Rule | Result |",
                "|---|---:|---:|---|---|",
            ]
        )
        for check in gate["checks"]:
            result = "PASS" if check["passed"] else "FAIL"
            lines.append(
                f"| `{check['metric']}` | {check['baseline']:.6f} | "
                f"{check['candidate']:.6f} | {check['rule']} | **{result}** |"
            )
    lines.extend(["", "## Trace Links", ""])
    if run.get("trace_ids"):
        lines.extend(f"- `{trace_id}`" for trace_id in run["trace_ids"])
    else:
        lines.append("- No LangSmith/provider trace IDs attached (offline deterministic run).")
    lines.append("")
    return "\n".join(lines)


def write_run_report(
    out_dir: Path,
    run: dict[str, Any],
    gate: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{run['run_id']}.json"
    md_path = out_dir / f"{run['run_id']}.md"
    json_path.write_text(canonical_json({"run": run, "gate": gate}), encoding="utf-8")
    md_path.write_text(render_markdown(run, gate), encoding="utf-8")
    return json_path, md_path
