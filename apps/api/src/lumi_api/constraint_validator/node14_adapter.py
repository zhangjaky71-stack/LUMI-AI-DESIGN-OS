from __future__ import annotations

from lumi_api.constraints.models import Constraint

from .contracts import RuntimeConstraint, RuntimeScope


def from_node14_constraint(value: Constraint) -> RuntimeConstraint:
    region: dict[str, float] | None = None
    if value.scope.region is not None:
        dumped = value.scope.region.model_dump(mode="json")
        region = {key: float(item) for key, item in dumped.items()}
    return RuntimeConstraint(
        constraint_id=str(value.id),
        type=value.type,
        severity=value.severity,
        scope=RuntimeScope(
            node_ids=tuple(str(item) for item in value.scope.node_ids),
            semantic_tags=value.scope.semantic_tags,
            region=region,
        ),
        parameters=dict(value.parameters),
        active=value.active,
    )


def from_node14_constraints(values: tuple[Constraint, ...]) -> tuple[RuntimeConstraint, ...]:
    return tuple(from_node14_constraint(value) for value in values)
