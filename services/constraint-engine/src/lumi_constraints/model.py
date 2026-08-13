from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Literal, Mapping

Severity = Literal["HARD", "SOFT", "ADVISORY"]
ConstraintSource = Literal[
    "SAFETY_SYSTEM",
    "USER_EXPLICIT",
    "APPROVED_BRAND_RULE",
    "PROJECT_RULE",
    "RECIPE_RULE",
    "AGENT_INFERRED",
    "STYLE_PREFERENCE",
]
PreflightDecision = Literal["ALLOW", "ALLOW_WITH_WARNINGS", "DENY"]
PostflightOutcome = Literal["PASS", "FAIL_REPAIRABLE", "FAIL_HARD"]


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set | frozenset):
        return frozenset(_freeze(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class ConstraintScope:
    node_ids: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()
    frame_ids: tuple[str, ...] = ()
    region: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_ids", tuple(dict.fromkeys(self.node_ids)))
        object.__setattr__(self, "roles", tuple(dict.fromkeys(self.roles)))
        object.__setattr__(self, "frame_ids", tuple(dict.fromkeys(self.frame_ids)))
        if self.region is not None:
            object.__setattr__(self, "region", _freeze(self.region))
        if not (self.node_ids or self.roles or self.frame_ids or self.region):
            raise ValueError("constraint scope cannot be empty")


@dataclass(frozen=True, slots=True)
class Constraint:
    id: str
    type: str
    scope: ConstraintScope
    severity: Severity
    source: ConstraintSource
    priority: int
    parameters: Mapping[str, Any]
    active: bool = True
    override_policy: Literal["NEVER", "AUTHORIZED"] = "AUTHORIZED"

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("constraint id is required")
        if not 0 <= self.priority <= 10000:
            raise ValueError("constraint priority must be 0..10000")
        object.__setattr__(self, "parameters", _freeze(self.parameters))
        if self.source == "SAFETY_SYSTEM" and self.override_policy != "NEVER":
            object.__setattr__(self, "override_policy", "NEVER")


@dataclass(frozen=True, slots=True)
class Violation:
    constraint_id: str
    type: str
    severity: Severity
    phase: Literal["PREFLIGHT", "POSTFLIGHT", "CONFLICT"]
    target_id: str | None
    expected: Mapping[str, Any]
    actual: Mapping[str, Any]
    message_code: str
    repair_hint: Mapping[str, Any]
    overrideable: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "expected", _freeze(self.expected))
        object.__setattr__(self, "actual", _freeze(self.actual))
        object.__setattr__(self, "repair_hint", _freeze(self.repair_hint))


@dataclass(frozen=True, slots=True)
class PreflightResult:
    decision: PreflightDecision
    candidate_document: Mapping[str, Any] | None
    candidate_document_version: int | None
    violations: tuple[Violation, ...]
    warnings: tuple[Violation, ...]


@dataclass(frozen=True, slots=True)
class PostflightEvidence:
    constraint_id: str
    kind: str
    passed: bool
    actual: Mapping[str, Any]
    repairable: bool
    evidence_ref: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "actual", _freeze(self.actual))


@dataclass(frozen=True, slots=True)
class PostflightResult:
    outcome: PostflightOutcome
    violations: tuple[Violation, ...]
    warnings: tuple[Violation, ...]


@dataclass(frozen=True, slots=True)
class OverrideAudit:
    override_id: str
    constraint_id: str
    actor_id: str
    reason: str
    occurred_at: datetime
    authorized: Literal[True] = True
