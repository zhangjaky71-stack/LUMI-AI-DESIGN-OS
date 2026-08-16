from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/nodes/NODE-28/generated-schemas"
DRAFT = "https://json-schema.org/draft/2020-12/schema"
UUID = {"type": "string", "format": "uuid"}


def object_schema(title: str, properties: dict, required: list[str]) -> dict:
    return {
        "$schema": DRAFT,
        "title": title,
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.schema.json"):
        old.unlink()

    state_properties = {
        "run_id": {"type": "string"},
        "organization_id": {"type": "string"},
        "project_id": {"type": "string"},
        "task_id": {"type": ["string", "null"]},
        "brief_version": {"type": "integer", "minimum": 1},
        "recipe_version": {"type": ["string", "null"]},
        "current_task_ids": {"type": "array", "items": {"type": "string"}},
        "approval_id": {"type": ["string", "null"]},
        "status": {"type": "string"},
        "context_refs": {"type": "array", "items": {"type": "string"}},
        "artifact_refs": {"type": "array", "items": {"type": "string"}},
        "budget_remaining": {"type": "string"},
        "errors": {"type": "array", "items": {"type": "object"}},
        "graph_key": {"type": "string"},
        "graph_version": {"type": "string"},
        "code_git_sha": {"type": "string"},
        "route": {"type": "string"},
        "external_job_id": {"type": ["string", "null"]},
        "repair_iteration": {"type": "integer", "minimum": 0},
        "max_repair_iterations": {"type": "integer", "minimum": 0},
    }
    schemas = {
        "run-state": object_schema("LumiRunState", state_properties, []),
        "start-run-command": object_schema(
            "StartRunCommand",
            {
                "organization_id": UUID,
                "project_id": UUID,
                "agent_run_id": UUID,
                "operation_id": UUID,
                "brief_version": {"type": "integer", "minimum": 1},
                "budget_remaining": {"type": "string"},
                "graph_key": {"type": "string"},
                "graph_version": {"type": "string"},
                "agent_config_version": {"type": "string"},
                "code_git_sha": {"type": "string"},
                "task_id": {"oneOf": [UUID, {"type": "null"}]},
                "thread_id": {"type": ["string", "null"]},
            },
            [
                "organization_id",
                "project_id",
                "agent_run_id",
                "operation_id",
                "brief_version",
                "budget_remaining",
                "graph_key",
                "graph_version",
                "agent_config_version",
                "code_git_sha",
            ],
        ),
        "resume-run-command": object_schema(
            "ResumeRunCommand",
            {
                "organization_id": UUID,
                "project_id": UUID,
                "agent_run_id": UUID,
                "operation_id": UUID,
                "thread_id": {"type": "string"},
                "resume_version": {"type": "integer", "minimum": 1},
                "interrupt_id": {"type": "string"},
                "kind": {"enum": ["approval", "external_job", "input"]},
                "value": {},
                "expected_graph_key": {"type": "string"},
                "expected_graph_version": {"type": "string"},
                "expected_code_git_sha": {"type": "string"},
            },
            [
                "organization_id",
                "project_id",
                "agent_run_id",
                "operation_id",
                "thread_id",
                "resume_version",
                "interrupt_id",
                "kind",
                "value",
                "expected_graph_key",
                "expected_graph_version",
                "expected_code_git_sha",
            ],
        ),
        "interrupt": object_schema(
            "GraphInterrupt",
            {
                "id": {"type": "string"},
                "kind": {"type": "string"},
                "node": {"type": ["string", "null"]},
                "payload": {"type": "object"},
                "resumable": {"type": "boolean"},
            },
            ["id", "kind", "payload", "resumable"],
        ),
        "run-control-snapshot": object_schema(
            "RunControlSnapshot",
            {
                "organization_id": UUID,
                "project_id": UUID,
                "agent_run_id": UUID,
                "thread_id": {"type": "string"},
                "graph_key": {"type": "string"},
                "graph_version": {"type": "string"},
                "code_git_sha": {"type": "string"},
                "status": {"type": "string"},
                "checkpoint_id": {"type": ["string", "null"]},
                "checkpoint_namespace": {"type": "string"},
                "state": {"$ref": "run-state.schema.json"},
                "next_nodes": {"type": "array", "items": {"type": "string"}},
                "interrupts": {"type": "array", "items": {"$ref": "interrupt.schema.json"}},
                "resume_version": {"type": "integer", "minimum": 1},
            },
            [
                "organization_id",
                "project_id",
                "agent_run_id",
                "thread_id",
                "graph_key",
                "graph_version",
                "code_git_sha",
                "status",
                "checkpoint_namespace",
                "state",
                "next_nodes",
                "interrupts",
                "resume_version",
            ],
        ),
        "safe-run-event": object_schema(
            "SafeRunEvent",
            {
                "event_type": {
                    "enum": [
                        "run.started",
                        "node.started",
                        "agent.status",
                        "agent.delta",
                        "tool.call",
                        "task.progress",
                        "approval.required",
                        "artifact.created",
                        "run.completed",
                        "run.cancelled",
                        "run.waiting_external",
                    ]
                },
                "organization_id": UUID,
                "project_id": UUID,
                "agent_run_id": UUID,
                "occurred_at": {"type": "string", "format": "date-time"},
                "payload": {"type": "object"},
            },
            ["event_type", "organization_id", "project_id", "agent_run_id", "payload"],
        ),
    }

    assert len(schemas) == 6
    for name, schema in schemas.items():
        path = OUT / f"{name}.schema.json"
        path.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"NODE-28 exported {len(schemas)} schemas to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
