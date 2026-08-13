from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from lumi_agent_runtime.recipe_engine import (
    CompiledRecipe,
    JoinPolicy,
    RecipeDefinition,
    RecipeProvenance,
    RecipeStep,
    StepType,
    TaskGraphTemplate,
    TaskTemplate,
)
from lumi_agent_runtime.task_graph import (
    InMemoryTaskGraphStore,
    TaskGraphBudgetError,
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


def compiled_parallel() -> CompiledRecipe:
    definition = RecipeDefinition(
        recipe_id="parallel-test",
        version="1.0.0",
        inputs=("brief",),
        steps=(
            RecipeStep(
                step_id="renders",
                step_type=StepType.PARALLEL,
                children=(),
            ),
        ),
    )
    tasks = tuple(
        TaskTemplate(
            task_key=f"renders.{name}",
            recipe_step_id="renders",
            step_type=StepType.MEDIA_JOB,
            owner="MEDIA_WORKER",
            depends_on=(),
            input_bindings={},
            output_schema="DesignOutput",
            budget_limit_usd="1",
            metadata={
                "parallel_group": "renders",
                "parallel_index": index,
                "max_parallel": 2,
                "media_operation": "image.generate",
            },
        )
        for index, name in enumerate(("a", "b", "c"))
    )
    graph = TaskGraphTemplate(
        recipe_id=definition.recipe_id,
        recipe_version=definition.version,
        tasks=tasks,
        recipe_budget_limit_usd="3",
        outputs={},
    )
    provenance = RecipeProvenance(
        requested_ref="parallel-test@1.0.0",
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


def single_task_store() -> tuple[InMemoryTaskGraphStore, object, datetime]:
    now = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
    definition = RecipeDefinition(
        recipe_id="single-test",
        version="1.0.0",
        inputs=("brief",),
        steps=(
            RecipeStep(
                step_id="review",
                step_type=StepType.APPROVAL,
                approval=None,
            ),
        ),
    )
    graph = TaskGraphTemplate(
        recipe_id=definition.recipe_id,
        recipe_version=definition.version,
        tasks=(
            TaskTemplate(
                task_key="review",
                recipe_step_id="review",
                step_type=StepType.APPROVAL,
                owner="HUMAN",
                depends_on=(),
                input_bindings={},
                output_schema="ApprovalResult",
            ),
        ),
        recipe_budget_limit_usd="1",
        outputs={},
    )
    provenance = RecipeProvenance(
        requested_ref="single-test@1.0.0",
        recipe_id=definition.recipe_id,
        exact_version=definition.version,
        recipe_definition_hash=definition.content_hash,
        release_manifest_revision=1,
        agents=(),
        skills=(),
        subrecipes=(),
        task_graph_template_hash=graph.content_hash,
    )
    bundle = instantiate_compiled_recipe(
        CompiledRecipe(definition=definition, task_graph=graph, provenance=provenance),
        organization_id=uuid4(),
        project_id=uuid4(),
        agent_run_id=uuid4(),
    )
    store = InMemoryTaskGraphStore()
    store.install(bundle)
    return store, bundle, now


class TaskGraphControlTests(unittest.TestCase):
    def test_parallel_claim_respects_max_inflight(self) -> None:
        bundle = instantiate_compiled_recipe(
            compiled_parallel(),
            organization_id=uuid4(),
            project_id=uuid4(),
            agent_run_id=uuid4(),
        )
        store = InMemoryTaskGraphStore()
        store.install(bundle)
        claimed = claim_ready_tasks(
            store,
            bundle.graph.graph_id,
            worker_id="parallel-worker",
            now=datetime(2026, 8, 13, 12, 0, tzinfo=UTC),
            limit=3,
        )
        self.assertEqual(len(claimed), 2)
        self.assertEqual({item.concurrency_group for item in claimed}, {"renders"})

    def test_wait_and_resume_are_explicit_states(self) -> None:
        store, bundle, now = single_task_store()
        claimed = claim_ready_tasks(
            store,
            bundle.graph.graph_id,
            worker_id="approval-worker",
            now=now,
        )[0]
        waited = wait_task(
            store,
            claimed.task_id,
            worker_id="approval-worker",
            now=now,
            target=TaskState.WAITING_APPROVAL,
            reason="human_review",
            external_ref="approval://123",
        )
        self.assertEqual(waited.status, TaskState.WAITING_APPROVAL)
        self.assertEqual(store.graph(bundle.graph.graph_id).status, TaskGraphState.WAITING)
        resumed = resume_waiting_task(
            store,
            claimed.task_id,
            now=now,
            resume_ref="approval://123/decision",
        )
        self.assertEqual(resumed.status, TaskState.READY)

    def test_running_cancel_is_cooperative(self) -> None:
        store, bundle, now = single_task_store()
        claimed = claim_ready_tasks(
            store,
            bundle.graph.graph_id,
            worker_id="cancel-worker",
            now=now,
        )[0]
        request_graph_cancel(store, bundle.graph.graph_id, now=now)
        running = store.task(claimed.task_id)
        self.assertEqual(running.status, TaskState.RUNNING)
        self.assertIsNotNone(running.cancellation_requested_at)
        acknowledge_running_cancel(
            store,
            claimed.task_id,
            worker_id="cancel-worker",
            now=now,
        )
        self.assertEqual(store.graph(bundle.graph.graph_id).status, TaskGraphState.CANCELLED)

    def test_dynamic_child_is_bounded_and_budget_non_escalating(self) -> None:
        store, bundle, now = single_task_store()
        claimed = claim_ready_tasks(
            store,
            bundle.graph.graph_id,
            worker_id="dynamic-worker",
            now=now,
        )[0]
        parent = store.task(claimed.task_id)
        enabled = replace(
            parent,
            budget_limit_usd="2",
            dynamic_child_limit=1,
            state_version=parent.state_version + 1,
        )
        store.replace_task(enabled, expected_version=parent.state_version)
        child = expand_dynamic_task(
            store,
            parent.task_id,
            child_key="child-a",
            owner="AGENT:critic@1.0.0",
            step_type="AGENT",
            output_schema="CritiqueOutput",
            budget_limit_usd="1",
        )
        self.assertEqual(child.dynamic_depth, 1)
        self.assertEqual(store.graph(bundle.graph.graph_id).task_count, 2)
        with self.assertRaises(Exception):
            expand_dynamic_task(
                store,
                parent.task_id,
                child_key="child-b",
                owner="AGENT:critic@1.0.0",
                step_type="AGENT",
                output_schema="CritiqueOutput",
                budget_limit_usd="1",
            )
        store2, bundle2, now2 = single_task_store()
        claimed2 = claim_ready_tasks(
            store2,
            bundle2.graph.graph_id,
            worker_id="dynamic-worker",
            now=now2,
        )[0]
        parent2 = store2.task(claimed2.task_id)
        enabled2 = replace(
            parent2,
            budget_limit_usd="1",
            dynamic_child_limit=2,
            state_version=parent2.state_version + 1,
        )
        store2.replace_task(enabled2, expected_version=parent2.state_version)
        with self.assertRaises(TaskGraphBudgetError):
            expand_dynamic_task(
                store2,
                parent2.task_id,
                child_key="too-expensive",
                owner="AGENT:critic@1.0.0",
                step_type="AGENT",
                output_schema="CritiqueOutput",
                budget_limit_usd="2",
            )


if __name__ == "__main__":
    unittest.main()
