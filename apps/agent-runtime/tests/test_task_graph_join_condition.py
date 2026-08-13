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
    TaskState,
    instantiate_compiled_recipe,
    refresh_ready_tasks,
)

NOW = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)


def bundle_for_join(
    *,
    join_policy: str,
    min_success: int | None = None,
    condition: str | None = None,
):
    definition = RecipeDefinition(
        recipe_id="join-test",
        version="1.0.0",
        inputs=("brief",),
        steps=(RecipeStep(step_id="join", step_type=StepType.PARALLEL),),
    )
    metadata: dict[str, object] = {"join_policy": join_policy}
    if min_success is not None:
        metadata["min_success"] = min_success
    graph = TaskGraphTemplate(
        recipe_id=definition.recipe_id,
        recipe_version=definition.version,
        tasks=(
            TaskTemplate(
                task_key="a",
                recipe_step_id="a",
                step_type=StepType.AGENT,
                owner="AGENT:a@1.0.0",
                depends_on=(),
                input_bindings={},
                output_schema="GenericTaskOutput",
            ),
            TaskTemplate(
                task_key="b",
                recipe_step_id="b",
                step_type=StepType.AGENT,
                owner="AGENT:b@1.0.0",
                depends_on=(),
                input_bindings={},
                output_schema="GenericTaskOutput",
            ),
            TaskTemplate(
                task_key="c",
                recipe_step_id="c",
                step_type=StepType.AGENT,
                owner="AGENT:c@1.0.0",
                depends_on=(),
                input_bindings={},
                output_schema="GenericTaskOutput",
            ),
            TaskTemplate(
                task_key="join",
                recipe_step_id="join",
                step_type=StepType.PARALLEL,
                owner="JOIN",
                depends_on=("a", "b", "c"),
                input_bindings={},
                output_schema="GenericTaskOutput",
                condition=condition,
                metadata=metadata,
            ),
        ),
        recipe_budget_limit_usd="1",
        outputs={},
    )
    provenance = RecipeProvenance(
        requested_ref="join-test@1.0.0",
        recipe_id=definition.recipe_id,
        exact_version=definition.version,
        recipe_definition_hash=definition.content_hash,
        release_manifest_revision=1,
        agents=(),
        skills=(),
        subrecipes=(),
        task_graph_template_hash=graph.content_hash,
    )
    return instantiate_compiled_recipe(
        CompiledRecipe(definition=definition, task_graph=graph, provenance=provenance),
        organization_id=uuid4(),
        project_id=uuid4(),
        agent_run_id=uuid4(),
    )


class TaskGraphJoinConditionTests(unittest.TestCase):
    def _store(self, **kwargs):
        bundle = bundle_for_join(**kwargs)
        store = InMemoryTaskGraphStore()
        store.install(bundle)
        return store, bundle

    def _set_state(self, store, task_key: str, status: TaskState, output=None) -> None:
        task = next(item for item in store.tasks(next(iter(store._graphs))) if item.task_key == task_key)
        store.replace_task(
            replace(
                task,
                status=status,
                output=output or {},
                state_version=task.state_version + 1,
            ),
            expected_version=task.state_version,
        )

    def test_all_join_requires_all_success(self) -> None:
        store, bundle = self._store(join_policy="ALL")
        for key in ("a", "b", "c"):
            self._set_state(store, key, TaskState.SUCCEEDED)
        refresh_ready_tasks(store, bundle.graph.graph_id, now=NOW)
        join = next(item for item in store.tasks(bundle.graph.graph_id) if item.task_key == "join")
        self.assertEqual(join.status, TaskState.READY)

    def test_any_join_ready_after_one_success(self) -> None:
        store, bundle = self._store(join_policy="ANY")
        self._set_state(store, "a", TaskState.SUCCEEDED)
        refresh_ready_tasks(store, bundle.graph.graph_id, now=NOW)
        join = next(item for item in store.tasks(bundle.graph.graph_id) if item.task_key == "join")
        self.assertEqual(join.status, TaskState.READY)

    def test_min_success_join(self) -> None:
        store, bundle = self._store(join_policy="MIN_SUCCESS", min_success=2)
        self._set_state(store, "a", TaskState.SUCCEEDED)
        self._set_state(store, "b", TaskState.SUCCEEDED)
        refresh_ready_tasks(store, bundle.graph.graph_id, now=NOW)
        join = next(item for item in store.tasks(bundle.graph.graph_id) if item.task_key == "join")
        self.assertEqual(join.status, TaskState.READY)

    def test_impossible_min_success_skips(self) -> None:
        store, bundle = self._store(join_policy="MIN_SUCCESS", min_success=2)
        self._set_state(store, "a", TaskState.FAILED_FINAL)
        self._set_state(store, "b", TaskState.FAILED_FINAL)
        refresh_ready_tasks(store, bundle.graph.graph_id, now=NOW)
        join = next(item for item in store.tasks(bundle.graph.graph_id) if item.task_key == "join")
        self.assertEqual(join.status, TaskState.SKIPPED)

    def test_safe_condition_uses_prior_output(self) -> None:
        store, bundle = self._store(
            join_policy="ANY",
            condition="steps.a.score >= 80",
        )
        self._set_state(store, "a", TaskState.SUCCEEDED, {"score": 90})
        refresh_ready_tasks(store, bundle.graph.graph_id, now=NOW)
        join = next(item for item in store.tasks(bundle.graph.graph_id) if item.task_key == "join")
        self.assertEqual(join.status, TaskState.READY)

    def test_false_condition_skips(self) -> None:
        store, bundle = self._store(
            join_policy="ANY",
            condition="steps.a.score >= 80",
        )
        self._set_state(store, "a", TaskState.SUCCEEDED, {"score": 20})
        refresh_ready_tasks(store, bundle.graph.graph_id, now=NOW)
        join = next(item for item in store.tasks(bundle.graph.graph_id) if item.task_key == "join")
        self.assertEqual(join.status, TaskState.SKIPPED)


if __name__ == "__main__":
    unittest.main()
