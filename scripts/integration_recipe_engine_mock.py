from __future__ import annotations

from typing import Any

from integration_recipe_engine import build_compiler

from lumi_agent_runtime.recipe_engine import StepType, TaskGraphTemplate


def resolve_reference(
    reference: str,
    *,
    inputs: dict[str, Any],
    results: dict[str, Any],
) -> Any:
    if not reference.startswith("$"):
        raise ValueError("mock executor only accepts compiled references")
    parts = reference[1:].split(".")
    if parts[0] == "inputs":
        value: Any = inputs[parts[1]]
        tail = parts[2:]
    elif parts[0] == "steps":
        value = results[parts[1]]
        tail = parts[2:]
        if tail and tail[0] == "output":
            tail = tail[1:]
    else:
        raise ValueError(f"mock executor root unsupported: {parts[0]}")
    for part in tail:
        if not isinstance(value, dict):
            raise ValueError(f"cannot traverse {reference}")
        value = value[part]
    return value


def run_mock(graph: TaskGraphTemplate, inputs: dict[str, Any]) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for task in graph.tasks:
        for dependency in task.depends_on:
            if dependency not in results:
                raise AssertionError(
                    f"task {task.task_key} ran before dependency {dependency}"
                )
        bound = {
            key: resolve_reference(value, inputs=inputs, results=results)
            for key, value in task.input_bindings.items()
        }
        if task.owner == "JOIN":
            output = {
                "items": [results[dependency] for dependency in task.depends_on],
                "join_policy": task.metadata["join_policy"],
            }
        elif task.step_type == StepType.APPROVAL:
            approval = task.metadata["approval"]
            assert isinstance(approval, dict)
            assert "approve" in approval["allowed_actions"]
            output = {
                "decision": "approved",
                "resume_value": approval["resume_mapping"]["approve"],
            }
        elif task.step_type == StepType.AGENT:
            output = {
                "kind": "agent",
                "owner": task.owner,
                "inputs": bound,
                "task": task.task_key,
            }
        elif task.step_type == StepType.MEDIA_JOB:
            output = {
                "kind": "media",
                "operation": task.metadata["media_operation"],
                "artifact_ref": f"artifact://mock/{task.task_key}",
                "inputs": bound,
            }
        elif task.step_type == StepType.QUALITY_GATE:
            output = {
                "passed": True,
                "metrics": dict(task.metadata["thresholds"]),
            }
        else:
            output = {
                "kind": "service",
                "owner": task.owner,
                "inputs": bound,
                "artifact_ref": f"artifact://mock/{task.task_key}",
            }
        results[task.task_key] = output
    return {
        name: resolve_reference(reference, inputs=inputs, results=results)
        for name, reference in graph.outputs.items()
    }


def main() -> int:
    compiler = build_compiler()
    compiled = compiler.compile("poster-campaign@production")
    outputs = run_mock(
        compiled.task_graph,
        inputs={"brief": {"goal": "synthetic poster campaign"}},
    )
    campaign = outputs["campaign"]
    assert campaign["kind"] == "service"
    assert campaign["owner"] == "DETERMINISTIC_SERVICE:campaign.finalize"
    assert campaign["artifact_ref"] == "artifact://mock/finalize"
    assert len(compiled.provenance.freeze_hash) == 64
    print("NODE-32 deterministic mock Recipe E2E: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
