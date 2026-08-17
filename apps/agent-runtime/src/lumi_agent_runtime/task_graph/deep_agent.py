from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from lumi_agent_runtime.deep_runtime.contracts import (
    DeepAgentInvocationContext,
    DeepAgentTaskRequest,
)

from .contracts import TaskKind, TaskSnapshot, TaskState
from .errors import TaskGraphStateError
from .store import TaskGraphStore


class ScheduledInvocationPolicy(Protocol):
    async def invocation_for(
        self,
        *,
        task: TaskSnapshot,
        state: dict[str, Any],
    ) -> DeepAgentInvocationContext: ...


class ScheduledAgentTaskRequestResolver:
    """NODE-29 `AgentTaskRequestResolver` backed by a claimed NODE-33 task."""

    def __init__(self, *, store: TaskGraphStore, policy: ScheduledInvocationPolicy) -> None:
        self.store = store
        self.policy = policy

    async def resolve(self, state: dict[str, Any]) -> DeepAgentTaskRequest:
        try:
            organization_id = UUID(str(state["organization_id"]))
            project_id = UUID(str(state["project_id"]))
            agent_run_id = UUID(str(state["run_id"]))
        except (KeyError, ValueError, TypeError) as exc:
            raise TaskGraphStateError("TASK_AGENT_STATE_IDENTITY_INVALID") from exc
        graph = await self.store.find_graph_by_run(
            organization_id=organization_id,
            agent_run_id=agent_run_id,
        )
        if graph is None or graph.project_id != project_id:
            raise TaskGraphStateError("TASK_AGENT_GRAPH_NOT_FOUND")
        selected = {str(value) for value in state.get("current_task_ids", [])}
        async with self.store.transaction(graph.graph_id) as tx:
            matches = [
                task
                for task in tx.tasks()
                if str(task.task_id) in selected
                and task.kind is TaskKind.AGENTIC
                and task.status is TaskState.RUNNING
            ]
        if len(matches) != 1:
            raise TaskGraphStateError("TASK_AGENT_CLAIM_SELECTION_INVALID")
        task = matches[0]
        if task.agent_ref is None or task.context_bundle_ref is None:
            raise TaskGraphStateError("TASK_AGENT_PIN_MISSING")
        invocation = await self.policy.invocation_for(task=task, state=state)
        if invocation.organization_id != task.organization_id:
            raise TaskGraphStateError("TASK_AGENT_ORGANIZATION_MISMATCH")
        if invocation.project_id != task.project_id:
            raise TaskGraphStateError("TASK_AGENT_PROJECT_MISMATCH")
        if invocation.agent_run_id != task.agent_run_id:
            raise TaskGraphStateError("TASK_AGENT_RUN_MISMATCH")
        if invocation.task_id != task.task_id:
            raise TaskGraphStateError("TASK_AGENT_TASK_ID_MISMATCH")
        agent_id = task.agent_ref.split("@", 1)[0]
        if invocation.root_agent != agent_id:
            raise TaskGraphStateError("TASK_AGENT_ROOT_ID_MISMATCH")
        return DeepAgentTaskRequest(
            agent_ref=task.agent_ref,
            objective=task.objective,
            context_bundle_ref=task.context_bundle_ref,
            invocation=invocation,
        )
