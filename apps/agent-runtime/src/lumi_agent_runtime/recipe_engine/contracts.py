from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

from lumi_agent_runtime.agent_registry.semver import SemVer

_ID = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_NAME = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")


class StepType(StrEnum):
    DETERMINISTIC = "DETERMINISTIC"
    AGENT = "AGENT"
    PARALLEL = "PARALLEL"
    FOREACH = "FOREACH"
    APPROVAL = "APPROVAL"
    QUALITY_GATE = "QUALITY_GATE"
    MEDIA_JOB = "MEDIA_JOB"
    SUBRECIPE = "SUBRECIPE"
    FINALIZE = "FINALIZE"


class JoinPolicy(StrEnum):
    ALL = "ALL"
    ANY = "ANY"
    MIN_SUCCESS = "MIN_SUCCESS"


class RecipeReleaseStatus(StrEnum):
    DRAFT = "DRAFT"
    CANDIDATE = "CANDIDATE"
    PRODUCTION = "PRODUCTION"
    DEPRECATED = "DEPRECATED"
    DISABLED = "DISABLED"


@dataclass(frozen=True, slots=True)
class LoopPolicy:
    max_iterations: int
    budget_limit_usd: str | None = None
    stop_condition: str | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.max_iterations <= 5:
            raise ValueError("RECIPE_LOOP_ITERATIONS_INVALID")
        _positive_decimal_or_none(self.budget_limit_usd, "RECIPE_LOOP_BUDGET_INVALID")
        if self.stop_condition is not None and not self.stop_condition:
            raise ValueError("RECIPE_LOOP_STOP_CONDITION_INVALID")


@dataclass(frozen=True, slots=True)
class ParallelPolicy:
    max_parallel: int
    join_policy: JoinPolicy = JoinPolicy.ALL
    min_success: int | None = None
    budget_limit_usd: str | None = None
    budget_split: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 1 <= self.max_parallel <= 8:
            raise ValueError("RECIPE_PARALLEL_LIMIT_INVALID")
        if self.join_policy == JoinPolicy.MIN_SUCCESS:
            if self.min_success is None or self.min_success < 1:
                raise ValueError("RECIPE_PARALLEL_MIN_SUCCESS_REQUIRED")
        elif self.min_success is not None:
            raise ValueError("RECIPE_PARALLEL_MIN_SUCCESS_FORBIDDEN")
        _positive_decimal_or_none(self.budget_limit_usd, "RECIPE_PARALLEL_BUDGET_INVALID")
        for value in self.budget_split:
            _positive_decimal_or_none(value, "RECIPE_PARALLEL_SPLIT_INVALID")


@dataclass(frozen=True, slots=True)
class ApprovalPolicy:
    prompt_summary: str
    allowed_actions: tuple[str, ...]
    artifact_refs: tuple[str, ...] = ()
    option_refs: tuple[str, ...] = ()
    expiry_seconds: int | None = None
    resume_mapping: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.prompt_summary or len(self.prompt_summary) > 1000:
            raise ValueError("RECIPE_APPROVAL_PROMPT_INVALID")
        if not self.allowed_actions or len(set(self.allowed_actions)) != len(self.allowed_actions):
            raise ValueError("RECIPE_APPROVAL_ACTIONS_INVALID")
        if self.expiry_seconds is not None and not 60 <= self.expiry_seconds <= 604800:
            raise ValueError("RECIPE_APPROVAL_EXPIRY_INVALID")
        if set(self.resume_mapping) - set(self.allowed_actions):
            raise ValueError("RECIPE_APPROVAL_RESUME_MAPPING_INVALID")


@dataclass(frozen=True, slots=True)
class QualityGatePolicy:
    metrics: tuple[str, ...]
    thresholds: dict[str, float | int]
    repair_recipe: str | None = None
    max_repair_iterations: int = 0

    def __post_init__(self) -> None:
        if not self.metrics or len(set(self.metrics)) != len(self.metrics):
            raise ValueError("RECIPE_QUALITY_METRICS_INVALID")
        if set(self.thresholds) - set(self.metrics):
            raise ValueError("RECIPE_QUALITY_THRESHOLD_UNKNOWN")
        if not 0 <= self.max_repair_iterations <= 3:
            raise ValueError("RECIPE_QUALITY_REPAIR_LIMIT_INVALID")
        if self.repair_recipe is None and self.max_repair_iterations:
            raise ValueError("RECIPE_QUALITY_REPAIR_RECIPE_REQUIRED")


@dataclass(frozen=True, slots=True)
class RecipeStep:
    step_id: str
    step_type: StepType
    depends_on: tuple[str, ...] = ()
    input_bindings: dict[str, str] = field(default_factory=dict)
    output_schema: str = "GenericTaskOutput"
    condition: str | None = None
    budget_limit_usd: str | None = None
    agent_ref: str | None = None
    skill_refs: tuple[str, ...] = ()
    service_key: str | None = None
    media_operation: str | None = None
    recipe_ref: str | None = None
    parallel: ParallelPolicy | None = None
    children: tuple[RecipeStep, ...] = ()
    foreach_count: int | None = None
    template: RecipeStep | None = None
    approval: ApprovalPolicy | None = None
    quality_gate: QualityGatePolicy | None = None
    loop: LoopPolicy | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _ID.fullmatch(self.step_id):
            raise ValueError(f"RECIPE_STEP_ID_INVALID:{self.step_id}")
        if len(set(self.depends_on)) != len(self.depends_on):
            raise ValueError("RECIPE_STEP_DEPENDENCY_DUPLICATE")
        if not self.output_schema or len(self.output_schema) > 128:
            raise ValueError("RECIPE_STEP_OUTPUT_SCHEMA_INVALID")
        _positive_decimal_or_none(self.budget_limit_usd, "RECIPE_STEP_BUDGET_INVALID")
        _json_guard(self.metadata, depth=0)

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.step_id,
            "type": self.step_type.value,
            "depends_on": list(self.depends_on),
            "input": self.input_bindings,
            "output_schema": self.output_schema,
            "condition": self.condition,
            "budget_limit_usd": self.budget_limit_usd,
            "agent_ref": self.agent_ref,
            "skill_refs": list(self.skill_refs),
            "service_key": self.service_key,
            "media_operation": self.media_operation,
            "recipe_ref": self.recipe_ref,
            "parallel": _parallel_payload(self.parallel),
            "children": [item.to_payload() for item in self.children],
            "foreach_count": self.foreach_count,
            "template": self.template.to_payload() if self.template else None,
            "approval": _approval_payload(self.approval),
            "quality_gate": _quality_payload(self.quality_gate),
            "loop": _loop_payload(self.loop),
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class RecipeDefinition:
    recipe_id: str
    version: str
    inputs: tuple[str, ...]
    steps: tuple[RecipeStep, ...]
    outputs: dict[str, str] = field(default_factory=dict)
    budget_limit_usd: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _ID.fullmatch(self.recipe_id):
            raise ValueError(f"RECIPE_ID_INVALID:{self.recipe_id}")
        SemVer.parse(self.version)
        if not self.inputs or len(set(self.inputs)) != len(self.inputs):
            raise ValueError("RECIPE_INPUTS_INVALID")
        if not self.steps or len(self.steps) > 128:
            raise ValueError("RECIPE_STEPS_INVALID")
        ids = [item.step_id for item in self.steps]
        if len(set(ids)) != len(ids):
            raise ValueError("RECIPE_STEP_ID_DUPLICATE")
        _positive_decimal_or_none(self.budget_limit_usd, "RECIPE_BUDGET_INVALID")
        _json_guard(self.metadata, depth=0)

    @property
    def identity(self) -> str:
        return f"{self.recipe_id}@{self.version}"

    @property
    def content_hash(self) -> str:
        payload = {
            "id": self.recipe_id,
            "version": self.version,
            "inputs": list(self.inputs),
            "steps": [item.to_payload() for item in self.steps],
            "outputs": self.outputs,
            "budget_limit_usd": self.budget_limit_usd,
            "metadata": self.metadata,
        }
        return _hash_json(payload)


@dataclass(frozen=True, slots=True)
class RecipeReleaseRecord:
    recipe_id: str
    version: str
    status: RecipeReleaseStatus
    eval_profile: str
    eval_status: str | None = None
    eval_evidence: str | None = None

    def __post_init__(self) -> None:
        SemVer.parse(self.version)
        if self.status == RecipeReleaseStatus.PRODUCTION and self.eval_status != "passed":
            raise ValueError("RECIPE_PRODUCTION_REQUIRES_PASSED_EVAL")


@dataclass(frozen=True, slots=True)
class RecipeReleaseManifest:
    schema: str
    revision: int
    releases: tuple[RecipeReleaseRecord, ...]
    aliases: dict[str, dict[str, str]]


@dataclass(frozen=True, slots=True)
class ResolvedRecipe:
    definition: RecipeDefinition
    release_status: RecipeReleaseStatus
    requested_ref: str
    manifest_revision: int


@dataclass(frozen=True, slots=True)
class ResolvedAgentBinding:
    requested_ref: str
    agent_id: str
    exact_version: str
    definition_hash: str
    provenance_hash: str


@dataclass(frozen=True, slots=True)
class ResolvedSkillBinding:
    requested_ref: str
    skill_id: str
    exact_version: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class TaskTemplate:
    task_key: str
    recipe_step_id: str
    step_type: StepType
    owner: str
    depends_on: tuple[str, ...]
    input_bindings: dict[str, str]
    output_schema: str
    condition: str | None = None
    budget_limit_usd: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TaskGraphTemplate:
    recipe_id: str
    recipe_version: str
    tasks: tuple[TaskTemplate, ...]
    recipe_budget_limit_usd: str | None
    outputs: dict[str, str]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        return _hash_json(
            {
                "recipe_id": self.recipe_id,
                "recipe_version": self.recipe_version,
                "recipe_budget_limit_usd": self.recipe_budget_limit_usd,
                "outputs": self.outputs,
                "metadata": self.metadata,
                "tasks": [
                    {
                        "task_key": item.task_key,
                        "recipe_step_id": item.recipe_step_id,
                        "step_type": item.step_type.value,
                        "owner": item.owner,
                        "depends_on": list(item.depends_on),
                        "input_bindings": item.input_bindings,
                        "output_schema": item.output_schema,
                        "condition": item.condition,
                        "budget_limit_usd": item.budget_limit_usd,
                        "metadata": item.metadata,
                    }
                    for item in self.tasks
                ],
            }
        )


@dataclass(frozen=True, slots=True)
class RecipeProvenance:
    requested_ref: str
    recipe_id: str
    exact_version: str
    recipe_definition_hash: str
    release_manifest_revision: int
    agents: tuple[ResolvedAgentBinding, ...]
    skills: tuple[ResolvedSkillBinding, ...]
    subrecipes: tuple[str, ...]
    task_graph_template_hash: str

    @property
    def freeze_hash(self) -> str:
        return _hash_json(
            {
                "requested_ref": self.requested_ref,
                "recipe_id": self.recipe_id,
                "exact_version": self.exact_version,
                "recipe_definition_hash": self.recipe_definition_hash,
                "release_manifest_revision": self.release_manifest_revision,
                "agents": [item.__dict__ for item in self.agents],
                "skills": [item.__dict__ for item in self.skills],
                "subrecipes": list(self.subrecipes),
                "task_graph_template_hash": self.task_graph_template_hash,
            }
        )


@dataclass(frozen=True, slots=True)
class CompiledRecipe:
    definition: RecipeDefinition
    task_graph: TaskGraphTemplate
    provenance: RecipeProvenance


def _positive_decimal_or_none(value: str | None, code: str) -> None:
    if value is None:
        return
    try:
        parsed = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(code) from exc
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError(code)


def _hash_json(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _parallel_payload(value: ParallelPolicy | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "max_parallel": value.max_parallel,
        "join_policy": value.join_policy.value,
        "min_success": value.min_success,
        "budget_limit_usd": value.budget_limit_usd,
        "budget_split": list(value.budget_split),
    }


def _approval_payload(value: ApprovalPolicy | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "prompt_summary": value.prompt_summary,
        "allowed_actions": list(value.allowed_actions),
        "artifact_refs": list(value.artifact_refs),
        "option_refs": list(value.option_refs),
        "expiry_seconds": value.expiry_seconds,
        "resume_mapping": value.resume_mapping,
    }


def _quality_payload(value: QualityGatePolicy | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "metrics": list(value.metrics),
        "thresholds": value.thresholds,
        "repair_recipe": value.repair_recipe,
        "max_repair_iterations": value.max_repair_iterations,
    }


def _loop_payload(value: LoopPolicy | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "max_iterations": value.max_iterations,
        "budget_limit_usd": value.budget_limit_usd,
        "stop_condition": value.stop_condition,
    }


def _json_guard(value: Any, *, depth: int) -> None:
    if depth > 16:
        raise ValueError("RECIPE_METADATA_TOO_DEEP")
    if value is None or isinstance(value, (str, int, bool)):
        return
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise ValueError("RECIPE_METADATA_NONFINITE")
        return
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("RECIPE_METADATA_NON_STRING_KEY")
        for child in value.values():
            _json_guard(child, depth=depth + 1)
        return
    if isinstance(value, (list, tuple)):
        for child in value:
            _json_guard(child, depth=depth + 1)
        return
    raise ValueError("RECIPE_METADATA_UNSUPPORTED")
