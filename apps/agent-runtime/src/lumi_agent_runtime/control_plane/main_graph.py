from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .contracts import LumiRunState, NodeCategory, RunStatus, validate_run_state
from .ports import ControlServices

GRAPH_KEY = "lumi.main"
GRAPH_VERSION = "1.0.0"
STATE_SCHEMA_VERSION = 1

NODE_CATEGORIES: dict[str, NodeCategory] = {
    "validate_run": NodeCategory.DETERMINISTIC,
    "load_project_snapshot": NodeCategory.DETERMINISTIC,
    "select_or_load_recipe": NodeCategory.DETERMINISTIC,
    "ensure_task_graph": NodeCategory.DETERMINISTIC,
    "route_ready_tasks": NodeCategory.DETERMINISTIC,
    "deterministic_task": NodeCategory.DETERMINISTIC,
    "deep_agent_task": NodeCategory.AGENTIC,
    "side_effect_task": NodeCategory.SIDE_EFFECT,
    "media_job_wait": NodeCategory.WAIT_EXTERNAL,
    "approval_interrupt": NodeCategory.HUMAN_INTERRUPT,
    "collect_results": NodeCategory.DETERMINISTIC,
    "quality_gate": NodeCategory.DETERMINISTIC,
    "finalize": NodeCategory.DETERMINISTIC,
}

_ALLOWED_TASK_ROUTES = {
    "deterministic": "deterministic_task",
    "agentic": "deep_agent_task",
    "side_effect": "side_effect_task",
    "wait_external": "media_job_wait",
    "approval": "approval_interrupt",
    "done": "collect_results",
}


def build_main_graph(*, services: ControlServices, checkpointer: Any):
    if checkpointer is None:
        raise ValueError("GRAPH_CHECKPOINTER_REQUIRED")

    async def validate_run(state: LumiRunState) -> dict[str, Any]:
        validate_run_state(state)
        if state.get("graph_key") != GRAPH_KEY or state.get("graph_version") != GRAPH_VERSION:
            raise ValueError("GRAPH_VERSION_MISMATCH")
        return {"status": RunStatus.RUNNING.value}

    async def load_project_snapshot(state: LumiRunState) -> dict[str, Any]:
        snapshot = await services.project.load_project_snapshot(state)
        refs = list(state.get("context_refs", []))
        ref = snapshot.get("context_ref")
        if ref:
            refs.append(str(ref))
        return {"context_refs": _unique(refs)}

    async def select_or_load_recipe(state: LumiRunState) -> dict[str, Any]:
        recipe = await services.recipes.select_recipe(state)
        version = recipe.get("version")
        if not version:
            raise ValueError("GRAPH_RECIPE_VERSION_REQUIRED")
        return {"recipe_version": str(version)}

    async def ensure_task_graph(state: LumiRunState) -> dict[str, Any]:
        task_ids = await services.tasks.ensure_task_graph(state)
        return {"current_task_ids": [str(item) for item in task_ids]}

    async def route_ready_tasks(state: LumiRunState) -> dict[str, Any]:
        route = await services.tasks.next_route(state)
        if route not in _ALLOWED_TASK_ROUTES:
            raise ValueError(f"GRAPH_TASK_ROUTE_INVALID:{route}")
        return {"route": route}

    async def deterministic_task(state: LumiRunState) -> dict[str, Any]:
        return _safe_delta(await services.deterministic.execute(state))

    async def deep_agent_task(state: LumiRunState) -> dict[str, Any]:
        return _safe_delta(await services.agentic.execute(state))

    async def side_effect_task(state: LumiRunState) -> dict[str, Any]:
        return _safe_delta(await services.side_effects.execute_idempotent(state))

    async def media_job_wait(state: LumiRunState) -> dict[str, Any]:
        job_id = state.get("external_job_id")
        if not job_id:
            job_id = await services.external_jobs.submit_idempotent(state)
        resume_value = interrupt(
            {
                "kind": "external_job",
                "run_id": state["run_id"],
                "job_id": job_id,
                "graph_version": state["graph_version"],
            }
        )
        if not isinstance(resume_value, dict) or resume_value.get("job_id") != job_id:
            raise ValueError("GRAPH_EXTERNAL_JOB_RESUME_INVALID")
        result = await services.external_jobs.collect_completed(
            {**state, "external_job_id": str(job_id)}
        )
        delta = _safe_delta(result)
        delta["external_job_id"] = None
        delta["status"] = RunStatus.RUNNING.value
        return delta

    async def approval_interrupt(state: LumiRunState) -> dict[str, Any]:
        resume_value = interrupt(
            {
                "kind": "approval",
                "run_id": state["run_id"],
                "approval_id": state.get("approval_id"),
                "graph_version": state["graph_version"],
                "allowed_actions": ["approve", "reject"],
            }
        )
        if not isinstance(resume_value, dict):
            raise ValueError("GRAPH_APPROVAL_RESUME_INVALID")
        action = resume_value.get("action")
        if action not in {"approve", "reject"}:
            raise ValueError("GRAPH_APPROVAL_ACTION_INVALID")
        if action == "reject":
            errors = list(state.get("errors", []))
            errors.append({"code": "APPROVAL_REJECTED"})
            return {"errors": errors, "route": "done"}
        return {"status": RunStatus.RUNNING.value, "route": "done"}

    async def collect_results(state: LumiRunState) -> dict[str, Any]:
        validate_run_state(state)
        return {"route": ""}

    async def quality_gate(state: LumiRunState) -> dict[str, Any]:
        decision = await services.quality.evaluate(state)
        if decision == "repair":
            iteration = int(state.get("repair_iteration", 0))
            maximum = int(state.get("max_repair_iterations", 2))
            if iteration >= maximum:
                return {"route": "approval"}
            return {"route": "repair", "repair_iteration": iteration + 1}
        if decision in {"approval", "finalize"}:
            return {"route": decision}
        raise ValueError(f"GRAPH_QUALITY_ROUTE_INVALID:{decision}")

    async def finalize(state: LumiRunState) -> dict[str, Any]:
        validate_run_state(state)
        return {"status": RunStatus.SUCCEEDED.value, "route": ""}

    graph = StateGraph(LumiRunState)
    for name, fn in {
        "validate_run": validate_run,
        "load_project_snapshot": load_project_snapshot,
        "select_or_load_recipe": select_or_load_recipe,
        "ensure_task_graph": ensure_task_graph,
        "route_ready_tasks": route_ready_tasks,
        "deterministic_task": deterministic_task,
        "deep_agent_task": deep_agent_task,
        "side_effect_task": side_effect_task,
        "media_job_wait": media_job_wait,
        "approval_interrupt": approval_interrupt,
        "collect_results": collect_results,
        "quality_gate": quality_gate,
        "finalize": finalize,
    }.items():
        graph.add_node(name, fn)

    graph.add_edge(START, "validate_run")
    graph.add_edge("validate_run", "load_project_snapshot")
    graph.add_edge("load_project_snapshot", "select_or_load_recipe")
    graph.add_edge("select_or_load_recipe", "ensure_task_graph")
    graph.add_edge("ensure_task_graph", "route_ready_tasks")
    graph.add_conditional_edges(
        "route_ready_tasks",
        lambda state: state["route"],
        _ALLOWED_TASK_ROUTES,
    )
    for task_node in (
        "deterministic_task",
        "deep_agent_task",
        "side_effect_task",
        "media_job_wait",
        "approval_interrupt",
    ):
        graph.add_edge(task_node, "collect_results")
    graph.add_edge("collect_results", "quality_gate")
    graph.add_conditional_edges(
        "quality_gate",
        lambda state: state["route"],
        {
            "repair": "route_ready_tasks",
            "approval": "approval_interrupt",
            "finalize": "finalize",
        },
    )
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=checkpointer)


def _safe_delta(delta: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(delta, dict):
        raise ValueError("GRAPH_NODE_DELTA_INVALID")
    candidate: LumiRunState = dict(delta)  # type: ignore[assignment]
    validate_run_state(candidate)
    return delta


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
