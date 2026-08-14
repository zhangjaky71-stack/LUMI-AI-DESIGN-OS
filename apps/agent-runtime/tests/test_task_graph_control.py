from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from lumi_agent_runtime.recipe_engine import (
    CompiledRecipe,
    RecipeDefinition,
    RecipeProvenance,
    RecipeStep,
    StepType,
    TaskGraphTemplate,
    TaskTemplate,
)
from lumi_agent_runtime.task_graph import (
    InMemoryTaskGraphStore,
    TaskGraphState,
    TaskState,
    acknowledge_running_cancel,
    claim_ready_tasks,
    expand_dynamic_task,
    instantiate_compiled_recipe,
    request_graph_cancel,
    resume_waiting_task,
    wait_task,
)
from lumi_agent_runtime.task_graph.errors import TaskGraphBudgetError, TaskGraphExpansionError


def compiled_control_recipe() -> CompiledRecipe:
    definition = RecipeDefinition(
        recipe_id="task-graph-control-test",
        version="1.0.0",
        inputs=("brief",),
        steps=(
            RecipeStep(
                step_id="work",
                step_type=StepType.AGENT,
                agent_ref="creative-director@1.1.0",
            ),
        ),
    )
    graph = TaskGraphTemplate(
        recipe_id=definition.recipe_id,
        recipe_version=definition.version,
        tasks=(
            TaskTemplate(
                task_key="work",
                recipe_step_id="work",
                step_type=StepType.AGENT,
                owner="AGENT:creative-director@1.1.0",
                depends_on=(),
                input_bindings={"brief": "$inputs.brief"},
                output_schema="DesignOutput",
                budget_limit_usd="5",
            ),
        ),
        recipe_budget_limit_usd="5",
        outputs={"artifact": "$steps.work.output"},
    )
    provenance = RecipeProvenance(
        requested_ref="task-graph-control-test@1.0.0",
        recipe_id=definition.recipe_id,
        exact_version=definition.version,
        recipe_definition_hash=definition.content_hash,
        release_manifest_revision=1,
        agents=(),
        skills=(),
        subrecipes=(),
        task_graph_template_hash=graph.content_hash,
    )
    return CompiledRecipe(definition=definition, task_graph=graph, provenance=provenance)


class TaskGraphControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 8, 14, 0, 0, tzinfo=UTC)
        self.bundle = instantiate_compiled_recipe(
            compiled_control_recipe(),
            organization_id=uuid4(),
            project_id=uuid4(),
            agent_run_id=uuid4(),
        )
        self.store = InMemoryTaskGraphStore()
        self.store.install(self.bundle)

    def test_wait_resume_and_cooperative_running_cancel(self) -> None:
        task = claim_ready_tasks(
            self.store,
            self.bundle.graph.graph_id,
            worker_id="worker-a",
            now=self.now,
        )[0]
        waiting = wait_task(
            self.store,
            task.task_id,
            worker_id="worker-a",
            now=self.now,
            target=TaskState.WAITING_APPROVAL,
            reason="human_review",
            external_ref="approval://node33/pending",
        )
        self.assertEqual(waiting.status, TaskState.WAITING_APPROVAL)
        resumed = resume_waiting_task(
            self.store,
            task.task_id,
            now=self.now,
            resume_ref="approval://node33/approved",
        )
        self.assertEqual(resumed.status, TaskState.READY)
        running = claim_ready_tasks(
            self.store,
            self.bundle.graph.graph_id,
            worker_id="worker-b",
            now=self.now,
        )[0]
        request_graph_cancel(self.store, self.bundle.graph.graph_id, now=self.now)
        marked = self.store.task(running.task_id)
        self.assertEqual(marked.status, TaskState.RUNNING)
        self.assertEqual(marked.cancellation_requested_at, self.now)
        cancelled = acknowledge_running_cancel(
            self.store,
            running.task_id,
            worker_id="worker-b",
            now=self.now,
        )
        self.assertEqual(cancelled.status, TaskState.CANCELLED)
        self.assertEqual(
            self.store.graph(self.bundle.graph.graph_id).status,
            TaskGraphState.CANCELLED,
        )

    def test_dynamic_child_limits_budget_and_concurrency_narrowing(self) -> None:
        task = claim_ready_tasks(
            self.store,
            self.bundle.graph.graph_id,
            worker_id="worker-a",
            now=self.now,
        )[0]
        parent = self.store.task(task.task_id)
        widened_parent = replace(
            parent,
            budget_limit_usd="5",
            dynamic_child_limit=1,
            concurrency_group="dynamic",
            concurrency_limit=2,
            state_version=parent.state_version + 1,
        )
        self.store.replace_task(widened_parent, expected_version=parent.state_version)

        with self.assertRaises(TaskGraphBudgetError):
            expand_dynamic_task(
                self.store,
                parent.task_id,
                child_key="too-expensive",
                owner=parent.owner,
                step_type="AGENT",
                output_schema="DesignOutput",
                budget_limit_usd="6",
                concurrency_limit=2,
            )
        with self.assertRaises(TaskGraphExpansionError):
            expand_dynamic_task(
                self.store,
                parent.task_id,
                child_key="too-wide",
                owner=parent.owner,
                step_type="AGENT",
                output_schema="DesignOutput",
                budget_limit_usd="4",
                concurrency_limit=3,
            )

        before = self.store.graph(parent.graph_id).task_count
        child = expand_dynamic_task(
            self.store,
            parent.task_id,
            child_key="safe-child",
            owner=parent.owner,
            step_type="AGENT",
            output_schema="DesignOutput",
            budget_limit_usd="4",
            concurrency_limit=2,
        )
        self.assertEqual(child.parent_task_id, parent.task_id)
        self.assertEqual(child.dynamic_depth, 1)
        self.assertEqual(self.store.graph(parent.graph_id).task_count, before + 1)
        with self.assertRaises(TaskGraphExpansionError):
            expand_dynamic_task(
                self.store,
                parent.task_id,
                child_key="second-child",
                owner=parent.owner,
                step_type="AGENT",
                output_schema="DesignOutput",
                budget_limit_usd="4",
                concurrency_limit=2,
            )


if __name__ == "__main__":
    unittest.main()
