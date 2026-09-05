from __future__ import annotations

from collections.abc import Mapping, Sequence

from .errors import InvariantViolation
from .ids import DomainId
from .value_objects import OperationIdentity


def _assert_acyclic(graph: Mapping[DomainId, Sequence[DomainId]], *, label: str) -> None:
    visiting: set[DomainId] = set()
    visited: set[DomainId] = set()

    def visit(node: DomainId) -> None:
        if node in visiting:
            raise InvariantViolation(f"{label} cannot contain a cycle")
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph.get(node, ()):
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)


def assert_artifact_lineage_acyclic(parents: Mapping[DomainId, Sequence[DomainId]]) -> None:
    _assert_acyclic(parents, label="artifact lineage")


def assert_task_graph_acyclic(dependencies: Mapping[DomainId, Sequence[DomainId]]) -> None:
    _assert_acyclic(dependencies, label="task dependency graph")


def require_tenant_membership(
    *, object_organization_id: DomainId, member_organization_ids: Sequence[DomainId]
) -> None:
    if object_organization_id not in member_organization_ids:
        raise InvariantViolation("tenant membership is required before object access")


def require_hard_constraint_override(*, violated: bool, override_audit_id: DomainId | None) -> None:
    if violated and override_audit_id is None:
        raise InvariantViolation("hard constraint requires an audited override")


def require_paid_operation_identity(*, paid: bool, operation: OperationIdentity | None) -> None:
    if paid and operation is None:
        raise InvariantViolation("paid side effect requires operation/idempotency identity")
