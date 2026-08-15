from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Protocol
from uuid import UUID

from .errors import InvariantViolation


class TenantScoped(Protocol):
    organization_id: UUID


def require_same_organization(*objects: TenantScoped) -> UUID:
    if not objects:
        raise ValueError("at least one object is required")
    organization_id = objects[0].organization_id
    if any(obj.organization_id != organization_id for obj in objects[1:]):
        raise InvariantViolation("cross-organization relationship is not allowed")
    return organization_id


def require_acyclic_graph(graph: Mapping[UUID, Iterable[UUID]], *, label: str) -> None:
    visited: set[UUID] = set()
    active: set[UUID] = set()

    def visit(node: UUID) -> None:
        if node in active:
            raise InvariantViolation(f"{label} cannot contain a cycle")
        if node in visited:
            return
        active.add(node)
        for dependency in graph.get(node, ()):  # missing leaves are valid external roots
            visit(dependency)
        active.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)


def require_task_graph_acyclic(graph: Mapping[UUID, Iterable[UUID]]) -> None:
    require_acyclic_graph(graph, label="task dependency graph")


def require_artifact_lineage_acyclic(graph: Mapping[UUID, Iterable[UUID]]) -> None:
    require_acyclic_graph(graph, label="artifact lineage")
