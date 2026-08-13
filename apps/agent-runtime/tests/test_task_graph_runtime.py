from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
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
    claim_ready_tasks,
    complete_task,
    fail_task,
    instantiate_compiled_recipe,
    schedule_retry,
    update_progress,
)


def compiled_two_step() -> CompiledRecipe:
    definition = RecipeDefinition(
        recipe_id="task-graph-test",
        version="1.0.0",
        inputs=("brief",),
        steps=(
            RecipeStep(
                step_id="work",
                step_type=StepType.AGENT,
                agent_ref="creative-director@1.1.0",
            ),
            RecipeStep(
                step_id="finalize",
                step_type=StepType.FINALIZE,
                service_key="artifact.finalize",
                depends_on=("work",),
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
                budget_limit_usd="2",
            ),
            TaskTemplate(
                task_key="finalize",
                recipe_step_id="finalize",
                step_type=StepType.FINALIZE,
                owner="DETERMINISTIC_SERVICE:artifact.finalize",
                depends_on=("work",),
                input_bindings={"artifact": "$steps.work.output"},
                output_schema="DesignOutput",
                budget_limit_usd="1",
            ),
        ),
        recipe_budget_limit_usd="3",
        outputs={"artifact": "$steps.finalize.output"},
    )
    provenance = RecipeProvenance(
        requested_ref="task-graph-test@1.0.0",
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


class TaskGraphRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
        self.bundle = instantiate_compiled_recipe(
            compiled_two_step(),
            organization_id=uuid4(),
            project_id=uuid4(),
            agent_run_id=uuid4(),
        )
        self.store = InMemoryTaskGraphStore()
        self.store.install(self.bundle)

    def test_dependency_order_progress_and_success(self) -> None:
        tasks = {item.task_key: item for item in self.store.tasks(self.bundle.graph.graph_id)}
        self.assertEqual(tasks["work"].status, TaskState.READY)
        self.assertEqual(tasks["finalize"].status, TaskState.PENDING)
        first = claim_ready_tasks(
            self.store,
            self.bundle.graph.graph_id,
            worker_id="worker-1",
            now=self.now,
        )[0]
        update_progress(
            self.store,
            first.task_id,
            worker_id="worker-1",
            now=self.now,
            current=1,
            total=2,
        )
        complete_task(
            self.store,
            first.task_id,
            worker_id="worker-1",
            now=self.now,
            output={"artifact_ref": "artifact://first"},
        )
        tasks = {item.task_key: item for item in self.store.tasks(self.bundle.graph.graph_id)}
        self.assertEqual(tasks["finalize"].status, TaskState.READY)
        self.assertEqual(self.store.graph(self.bundle.graph.graph_id).progress, 0.5)
        second = claim_ready_tasks(
            self.store,
            self.bundle.graph.graph_id,
            worker_id="worker-2",
            now=self.now,
        )[0]
        complete_task(
            self.store,
            second.task_id,
            worker_id="worker-2",
            now=self.now,
            output={"artifact_ref": "artifact://final"},
        )
        graph = self.store.graph(self.bundle.graph.graph_id)
        self.assertEqual(graph.status, TaskGraphState.SUCCEEDED)
        self.assertEqual(graph.progress, 1.0)

    def test_retry_reuses_logical_side_effect_operation_key(self) -> None:
        task = claim_ready_tasks(
            self.store,
            self.bundle.graph.graph_id,
            worker_id="worker-1",
            now=self.now,
        )[0]
        fail_task(
            self.store,
            task.task_id,
            worker_id="worker-1",
            now=self.now,
            retryable=True,
            error_category="provider_timeout",
        )
        schedule_retry(
            self.store,
            task.task_id,
            retry_not_before=self.now + timedelta(seconds=10),
        )
        retried = claim_ready_tasks(
            self.store,
            self.bundle.graph.graph_id,
            worker_id="worker-2",
            now=self.now + timedelta(seconds=11),
        )[0]
        self.assertEqual(retried.attempt_count, 2)
        attempts = self.store.attempts(task.task_id)
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0].operation_key, attempts[1].operation_key)

    def test_restart_uses_store_state_not_runtime_object_identity(self) -> None:
        first = claim_ready_tasks(
            self.store,
            self.bundle.graph.graph_id,
            worker_id="before-restart",
            now=self.now,
        )[0]
        complete_task(
            self.store,
            first.task_id,
            worker_id="before-restart",
            now=self.now,
            output={"ok": True},
        )
        recovered_store = self.store
        ready = [
            item
            for item in recovered_store.tasks(self.bundle.graph.graph_id)
            if item.status == TaskState.READY
        ]
        self.assertEqual([item.task_key for item in ready], ["finalize"])


if __name__ == "__main__":
    unittest.main()
