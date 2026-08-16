from __future__ import annotations

from dataclasses import dataclass
import re
from uuid import UUID

from lumi_api.domain.ids import new_uuid7

from .models import Constraint, ConstraintScope, ConstraintSet, ConstraintType

_LOCK_PHRASES = (
    "不要动",
    "别动",
    "保持不变",
    "不能变",
    "不可变",
    "do not move",
    "don't move",
    "do not change",
    "don't change",
    "keep unchanged",
    "keep intact",
)


@dataclass(frozen=True)
class ExplicitTarget:
    label: str
    node_id: UUID
    category: str = "generic"


def structure_explicit_user_locks(
    instruction: str,
    targets: tuple[ExplicitTarget, ...],
) -> ConstraintSet:
    normalized = instruction.casefold()
    clauses = [
        clause.strip()
        for clause in re.split(r"[，,。.;；\n]+", normalized)
        if clause.strip()
    ]

    constraints: list[Constraint] = []
    for target in targets:
        label = target.label.casefold()
        target_clauses = [clause for clause in clauses if label in clause]
        if not any(
            any(phrase in clause for phrase in _LOCK_PHRASES)
            for clause in target_clauses
        ):
            continue
        types: tuple[ConstraintType, ...]
        if target.category == "qr":
            types = ("LOCK_TRANSFORM", "LOCK_CONTENT", "REQUIRE_SCANNABILITY")
        elif target.category in {"logo", "product"}:
            types = ("LOCK_TRANSFORM", "LOCK_IDENTITY")
        elif target.category == "text":
            types = ("LOCK_TRANSFORM", "LOCK_TEXT")
        else:
            types = ("LOCK_TRANSFORM", "LOCK_CONTENT")
        for constraint_type in types:
            constraints.append(
                Constraint(
                    id=new_uuid7(),
                    type=constraint_type,
                    scope=ConstraintScope(node_ids=(target.node_id,)),
                    severity="HARD",
                    source="USER_EXPLICIT",
                    priority=1_000,
                    parameters={"origin": "explicit_instruction"},
                )
            )
    return ConstraintSet(constraints=tuple(constraints))
