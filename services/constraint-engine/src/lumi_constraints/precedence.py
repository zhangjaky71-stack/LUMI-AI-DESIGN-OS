from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from .model import Constraint, Violation
from .registry import SOURCE_PRECEDENCE


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_plain(item) for item in value]
    if isinstance(value, frozenset | set):
        return sorted(_plain(item) for item in value)
    return value


def scope_key(constraint: Constraint) -> str:
    payload = {
        "node_ids": sorted(constraint.scope.node_ids),
        "roles": sorted(constraint.scope.roles),
        "frame_ids": sorted(constraint.scope.frame_ids),
        "region": _plain(constraint.scope.region),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def precedence_key(constraint: Constraint) -> tuple[int, int]:
    return SOURCE_PRECEDENCE[constraint.source], constraint.priority


def detect_conflicts(constraints: Iterable[Constraint]) -> tuple[Violation, ...]:
    groups: dict[tuple[str, str, tuple[int, int]], list[Constraint]] = defaultdict(list)
    for constraint in constraints:
        if not constraint.active:
            continue
        groups[(constraint.type, scope_key(constraint), precedence_key(constraint))].append(constraint)

    violations: list[Violation] = []
    for (constraint_type, _, _), group in groups.items():
        if len(group) < 2:
            continue
        by_parameters: dict[str, list[Constraint]] = defaultdict(list)
        for constraint in group:
            encoded = json.dumps(_plain(constraint.parameters), sort_keys=True, separators=(",", ":"))
            by_parameters[encoded].append(constraint)
        if len(by_parameters) == 1:
            continue
        ids = sorted(constraint.id for constraint in group)
        severity = "HARD" if any(item.severity == "HARD" for item in group) else "SOFT"
        violations.append(
            Violation(
                constraint_id="|".join(ids),
                type=constraint_type,
                severity=severity,
                phase="CONFLICT",
                target_id=None,
                expected={"single_effective_rule": True},
                actual={"conflicting_constraint_ids": ids},
                message_code="CONSTRAINT_PRECEDENCE_CONFLICT",
                repair_hint={"action": "resolve_same_level_rule_conflict"},
                overrideable=False,
            )
        )
    return tuple(violations)


def effective_constraints(constraints: Iterable[Constraint]) -> tuple[Constraint, ...]:
    """Return one highest-precedence rule per (type, scope), preserving unlike rule types."""
    groups: dict[tuple[str, str], list[Constraint]] = defaultdict(list)
    for constraint in constraints:
        if constraint.active:
            groups[(constraint.type, scope_key(constraint))].append(constraint)

    selected: list[Constraint] = []
    for group in groups.values():
        ordered = sorted(
            group,
            key=lambda item: (precedence_key(item), item.id),
            reverse=True,
        )
        selected.append(ordered[0])
    return tuple(
        sorted(
            selected,
            key=lambda item: (precedence_key(item), item.type, scope_key(item), item.id),
            reverse=True,
        )
    )
