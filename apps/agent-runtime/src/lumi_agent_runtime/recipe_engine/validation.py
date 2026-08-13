from __future__ import annotations

import re

from .contracts import RecipeDefinition, RecipeStep
from .errors import (
    RecipeCycleError,
    RecipeDependencyError,
    RecipeReferenceError,
)
from .expression import validate_expression

_STEP_EXPR = re.compile(r"\bsteps\.([a-z][a-z0-9-]{0,62})\b")


def topological_steps(definition: RecipeDefinition) -> tuple[RecipeStep, ...]:
    by_id = {item.step_id: item for item in definition.steps}
    for step in definition.steps:
        missing = set(step.depends_on) - set(by_id)
        if missing:
            raise RecipeDependencyError(
                f"Recipe step {step.step_id} has missing dependencies: {sorted(missing)}"
            )
        if step.step_id in step.depends_on:
            raise RecipeCycleError(f"Recipe step depends on itself: {step.step_id}")
    visiting: list[str] = []
    visited: set[str] = set()
    ordered: list[RecipeStep] = []

    def visit(step_id: str) -> None:
        if step_id in visited:
            return
        if step_id in visiting:
            raise RecipeCycleError(
                "Recipe dependency cycle: " + " -> ".join((*visiting, step_id))
            )
        visiting.append(step_id)
        for dependency in sorted(by_id[step_id].depends_on):
            visit(dependency)
        visiting.pop()
        visited.add(step_id)
        ordered.append(by_id[step_id])

    for step_id in sorted(by_id):
        visit(step_id)
    return tuple(ordered)


def dependency_closure(step_id: str, definition: RecipeDefinition) -> frozenset[str]:
    by_id = {item.step_id: item for item in definition.steps}
    result: set[str] = set()

    def walk(current: str) -> None:
        for dependency in by_id[current].depends_on:
            if dependency not in result:
                result.add(dependency)
                walk(dependency)

    walk(step_id)
    return frozenset(result)


def validate_step_references(
    step: RecipeStep,
    definition: RecipeDefinition,
    available_sources: frozenset[str],
) -> None:
    for binding in step.input_bindings.values():
        validate_reference(binding, definition, available_sources)
    if step.condition is not None:
        validate_expression(step.condition)
        validate_expression_step_refs(step.condition, available_sources)
    if step.loop is not None and step.loop.stop_condition is not None:
        validate_expression(step.loop.stop_condition)
        validate_expression_step_refs(step.loop.stop_condition, available_sources)
    if step.approval is not None:
        for reference in (*step.approval.artifact_refs, *step.approval.option_refs):
            validate_reference(reference, definition, available_sources)


def validate_outputs(definition: RecipeDefinition) -> None:
    all_steps = frozenset(item.step_id for item in definition.steps)
    for reference in definition.outputs.values():
        validate_reference(reference, definition, all_steps)


def validate_reference(
    reference: str,
    definition: RecipeDefinition,
    available_sources: frozenset[str],
) -> None:
    if not reference.startswith("$"):
        raise RecipeReferenceError(f"Recipe binding must be a reference: {reference}")
    parts = reference[1:].split(".")
    if len(parts) < 2:
        raise RecipeReferenceError(f"Recipe reference incomplete: {reference}")
    root = parts[0]
    if root == "inputs":
        if parts[1] not in definition.inputs:
            raise RecipeReferenceError(f"Recipe input is not declared: {reference}")
        return
    if root in {"project", "run"}:
        return
    if root == "steps":
        source = parts[1]
        if source not in available_sources:
            raise RecipeReferenceError(
                f"Recipe step reference is not an upstream dependency: {reference}"
            )
        if len(parts) < 3 or parts[2] != "output":
            raise RecipeReferenceError(
                f"Recipe step reference must use .output: {reference}"
            )
        return
    raise RecipeReferenceError(f"Recipe reference root forbidden: {reference}")


def validate_expression_step_refs(
    expression: str,
    available_sources: frozenset[str],
) -> None:
    for source in _STEP_EXPR.findall(expression):
        if source not in available_sources:
            raise RecipeReferenceError(
                f"condition reads non-upstream step: {source}"
            )
