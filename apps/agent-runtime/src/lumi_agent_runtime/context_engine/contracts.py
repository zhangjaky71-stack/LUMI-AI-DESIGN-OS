from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping
from uuid import UUID

_HASH = re.compile(r"^[0-9a-f]{64}$")
_REF = re.compile(r"^[a-z][a-z0-9+.-]*://[^\s]{1,2040}$")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,99}$")
_AGENT_REF = re.compile(
    r"^[a-z][a-z0-9_-]{0,62}@[A-Za-z0-9][A-Za-z0-9_.+-]{0,99}$"
)
_MEMORY_SCOPE = re.compile(
    r"^(project|brand|user|organization)(:[A-Za-z0-9_.-]+)?$"
)


class ContextLayer(StrEnum):
    L0_SYSTEM = "L0_SYSTEM"
    L1_PROJECT = "L1_PROJECT"
    L2_AGENT = "L2_AGENT"
    L3_TASK = "L3_TASK"
    L4_RETRIEVED = "L4_RETRIEVED"


class ContextKind(StrEnum):
    SYSTEM_POLICY = "SYSTEM_POLICY"
    PROJECT_SUMMARY = "PROJECT_SUMMARY"
    BRAND_RULE = "BRAND_RULE"
    AGENT_INSTRUCTION = "AGENT_INSTRUCTION"
    SKILL = "SKILL"
    TASK_INPUT = "TASK_INPUT"
    FROZEN_TASK_CONTEXT = "FROZEN_TASK_CONTEXT"
    TASK_OUTPUT = "TASK_OUTPUT"
    ASSET = "ASSET"
    ARTIFACT = "ARTIFACT"
    RESEARCH = "RESEARCH"
    MEMORY = "MEMORY"
    KNOWLEDGE = "KNOWLEDGE"
    TOOL_RESULT = "TOOL_RESULT"


class TrustLevel(StrEnum):
    TRUSTED_SYSTEM = "TRUSTED_SYSTEM"
    TRUSTED_AGENT = "TRUSTED_AGENT"
    USER_INPUT = "USER_INPUT"
    TRUSTED_PROJECT_DATA = "TRUSTED_PROJECT_DATA"
    UNTRUSTED_RETRIEVED = "UNTRUSTED_RETRIEVED"


class InstructionAuthority(StrEnum):
    SYSTEM = "system"
    AGENT = "agent"
    USER = "user"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class ContextSourceRef:
    source_ref: str
    source_type: str
    source_id: str
    version: str
    content_hash: str

    def __post_init__(self) -> None:
        if not _REF.fullmatch(self.source_ref):
            raise ValueError("CONTEXT_SOURCE_REF_INVALID")
        if not self.source_type or len(self.source_type) > 80:
            raise ValueError("CONTEXT_SOURCE_TYPE_INVALID")
        if not self.source_id or len(self.source_id) > 255:
            raise ValueError("CONTEXT_SOURCE_ID_INVALID")
        if not _VERSION.fullmatch(self.version):
            raise ValueError("CONTEXT_SOURCE_VERSION_INVALID")
        if not _HASH.fullmatch(self.content_hash):
            raise ValueError("CONTEXT_SOURCE_HASH_INVALID")

    @property
    def version_key(self) -> str:
        return (
            f"{self.source_type}:{self.source_id}@{self.version}"
            f"#{self.content_hash}"
        )


@dataclass(frozen=True, slots=True)
class ContextItem:
    item_id: str
    layer: ContextLayer
    kind: ContextKind
    content: str
    source: ContextSourceRef
    trust: TrustLevel
    instruction_authority: InstructionAuthority
    priority: int = 100
    token_estimate: int = 0
    relevance_score: float = 0.0
    freshness_score: float = 0.0
    pinned: bool = False
    required: bool = False
    compressible: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.item_id or len(self.item_id) > 255:
            raise ValueError("CONTEXT_ITEM_ID_INVALID")
        if not isinstance(self.content, str) or len(self.content) > 256_000:
            raise ValueError("CONTEXT_ITEM_CONTENT_INVALID")
        if not 0 <= self.priority <= 1000:
            raise ValueError("CONTEXT_ITEM_PRIORITY_INVALID")
        if self.token_estimate < 0:
            raise ValueError("CONTEXT_ITEM_TOKEN_ESTIMATE_INVALID")
        for value in (self.relevance_score, self.freshness_score):
            if not isinstance(value, int | float) or not math.isfinite(value):
                raise ValueError("CONTEXT_ITEM_SCORE_INVALID")
            if not 0 <= float(value) <= 1:
                raise ValueError("CONTEXT_ITEM_SCORE_INVALID")
        _json_guard(dict(self.metadata))
        self._validate_authority()

    def _validate_authority(self) -> None:
        expected = {
            TrustLevel.TRUSTED_SYSTEM: InstructionAuthority.SYSTEM,
            TrustLevel.TRUSTED_AGENT: InstructionAuthority.AGENT,
            TrustLevel.USER_INPUT: InstructionAuthority.USER,
            TrustLevel.TRUSTED_PROJECT_DATA: InstructionAuthority.NONE,
            TrustLevel.UNTRUSTED_RETRIEVED: InstructionAuthority.NONE,
        }[self.trust]
        if self.instruction_authority is not expected:
            raise ValueError("CONTEXT_ITEM_AUTHORITY_INVALID")

    @property
    def rendered_content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class LayerBudget:
    layer: ContextLayer
    max_tokens: int
    required: bool = False

    def __post_init__(self) -> None:
        if not 1 <= self.max_tokens <= 1_000_000:
            raise ValueError("CONTEXT_LAYER_BUDGET_INVALID")


@dataclass(frozen=True, slots=True)
class ContextRequest:
    organization_id: UUID
    project_id: UUID
    agent_run_id: UUID
    task_id: UUID | None
    agent_ref: str
    context_bundle_ref: str
    objective: str
    purpose: str
    query: str
    max_input_tokens: int
    response_reserve_tokens: int
    static_prompt_tokens: int
    layer_budgets: tuple[LayerBudget, ...]
    memory_read_scopes: tuple[str, ...] = ()
    retrieval_limit: int = 12
    required_source_refs: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _AGENT_REF.fullmatch(self.agent_ref):
            raise ValueError("CONTEXT_REQUEST_AGENT_EXACT_REF_REQUIRED")
        if not self.context_bundle_ref.startswith("context-bundle://"):
            raise ValueError("CONTEXT_REQUEST_BUNDLE_REF_REQUIRED")
        if not _REF.fullmatch(self.context_bundle_ref):
            raise ValueError("CONTEXT_REQUEST_BUNDLE_REF_INVALID")
        if not self.objective or len(self.objective) > 64_000:
            raise ValueError("CONTEXT_REQUEST_OBJECTIVE_INVALID")
        if not self.purpose or len(self.purpose) > 255:
            raise ValueError("CONTEXT_REQUEST_PURPOSE_INVALID")
        if len(self.query) > 32_000:
            raise ValueError("CONTEXT_REQUEST_QUERY_INVALID")
        if self.max_input_tokens < 512:
            raise ValueError("CONTEXT_REQUEST_MAX_INPUT_INVALID")
        if not 64 <= self.response_reserve_tokens < self.max_input_tokens:
            raise ValueError("CONTEXT_REQUEST_RESPONSE_RESERVE_INVALID")
        if not 0 <= self.static_prompt_tokens < self.max_input_tokens:
            raise ValueError("CONTEXT_REQUEST_STATIC_PROMPT_INVALID")
        if self.dynamic_budget_tokens < 128:
            raise ValueError("CONTEXT_REQUEST_DYNAMIC_BUDGET_TOO_SMALL")
        if not 1 <= self.retrieval_limit <= 100:
            raise ValueError("CONTEXT_REQUEST_RETRIEVAL_LIMIT_INVALID")
        layers = tuple(item.layer for item in self.layer_budgets)
        if len(layers) != len(set(layers)):
            raise ValueError("CONTEXT_LAYER_BUDGET_DUPLICATE")
        if len(self.required_source_refs) != len(set(self.required_source_refs)):
            raise ValueError("CONTEXT_REQUIRED_SOURCE_DUPLICATE")
        for ref in self.required_source_refs:
            if not _REF.fullmatch(ref):
                raise ValueError("CONTEXT_REQUIRED_SOURCE_REF_INVALID")
        if len(self.memory_read_scopes) != len(set(self.memory_read_scopes)):
            raise ValueError("CONTEXT_MEMORY_SCOPE_DUPLICATE")
        for scope in self.memory_read_scopes:
            if not _MEMORY_SCOPE.fullmatch(scope):
                raise ValueError(f"CONTEXT_MEMORY_SCOPE_INVALID:{scope}")
        _json_guard(dict(self.metadata))

    @property
    def dynamic_budget_tokens(self) -> int:
        return (
            self.max_input_tokens
            - self.response_reserve_tokens
            - self.static_prompt_tokens
        )

    @property
    def semantic_hash(self) -> str:
        return stable_hash(
            {
                "organization_id": str(self.organization_id),
                "project_id": str(self.project_id),
                "agent_run_id": str(self.agent_run_id),
                "task_id": str(self.task_id) if self.task_id else None,
                "agent_ref": self.agent_ref,
                "context_bundle_ref": self.context_bundle_ref,
                "objective": self.objective,
                "purpose": self.purpose,
                "query": self.query,
                "max_input_tokens": self.max_input_tokens,
                "response_reserve_tokens": self.response_reserve_tokens,
                "static_prompt_tokens": self.static_prompt_tokens,
                "layer_budgets": [
                    {
                        "layer": item.layer.value,
                        "max_tokens": item.max_tokens,
                        "required": item.required,
                    }
                    for item in self.layer_budgets
                ],
                "memory_read_scopes": list(self.memory_read_scopes),
                "retrieval_limit": self.retrieval_limit,
                "required_source_refs": sorted(self.required_source_refs),
                "metadata": dict(self.metadata),
            }
        )


@dataclass(frozen=True, slots=True)
class ContextManifest:
    organization_id: UUID
    project_id: UUID
    agent_run_id: UUID
    task_id: UUID | None
    agent_ref: str
    context_bundle_ref: str
    context_bundle_hash: str
    request_hash: str
    items: tuple[ContextItem, ...]
    total_tokens: int
    max_tokens: int
    source_versions: tuple[str, ...]
    cache_key: str
    rendered_context: str
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _AGENT_REF.fullmatch(self.agent_ref):
            raise ValueError("CONTEXT_MANIFEST_AGENT_REF_INVALID")
        if not _REF.fullmatch(self.context_bundle_ref):
            raise ValueError("CONTEXT_MANIFEST_BUNDLE_REF_INVALID")
        if not _HASH.fullmatch(self.context_bundle_hash):
            raise ValueError("CONTEXT_MANIFEST_BUNDLE_HASH_INVALID")
        if not _HASH.fullmatch(self.request_hash):
            raise ValueError("CONTEXT_MANIFEST_REQUEST_HASH_INVALID")
        if not 0 <= self.total_tokens <= self.max_tokens:
            raise ValueError("CONTEXT_MANIFEST_BUDGET_INVALID")
        if not _HASH.fullmatch(self.cache_key):
            raise ValueError("CONTEXT_MANIFEST_CACHE_KEY_INVALID")
        if len(self.source_versions) != len(set(self.source_versions)):
            raise ValueError("CONTEXT_MANIFEST_SOURCE_VERSION_DUPLICATE")

    @property
    def freeze_hash(self) -> str:
        return stable_hash(
            {
                "organization_id": str(self.organization_id),
                "project_id": str(self.project_id),
                "agent_run_id": str(self.agent_run_id),
                "task_id": str(self.task_id) if self.task_id else None,
                "agent_ref": self.agent_ref,
                "context_bundle_ref": self.context_bundle_ref,
                "context_bundle_hash": self.context_bundle_hash,
                "request_hash": self.request_hash,
                "items": [
                    {
                        "item_id": item.item_id,
                        "layer": item.layer.value,
                        "kind": item.kind.value,
                        "source": item.source.version_key,
                        "trust": item.trust.value,
                        "authority": item.instruction_authority.value,
                        "priority": item.priority,
                        "token_estimate": item.token_estimate,
                        "content_hash": item.rendered_content_hash,
                        "metadata": dict(item.metadata),
                    }
                    for item in self.items
                ],
                "total_tokens": self.total_tokens,
                "max_tokens": self.max_tokens,
                "source_versions": list(self.source_versions),
                "cache_key": self.cache_key,
                "rendered_hash": hashlib.sha256(
                    self.rendered_context.encode("utf-8")
                ).hexdigest(),
                "warnings": list(self.warnings),
            }
        )

    @property
    def runtime_context_ref(self) -> str:
        task = str(self.task_id) if self.task_id else "run"
        return (
            f"runtime-context://{self.organization_id}/{self.project_id}/"
            f"{task}/{self.freeze_hash}"
        )


def stable_hash(value: Any) -> str:
    payload = json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _json_guard(value: Any, depth: int = 0) -> None:
    if depth > 24:
        raise ValueError("CONTEXT_JSON_TOO_DEEP")
    if value is None or isinstance(value, str | int | bool):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("CONTEXT_JSON_NONFINITE")
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("CONTEXT_JSON_NON_STRING_KEY")
            _json_guard(child, depth + 1)
        return
    if isinstance(value, tuple | list):
        for child in value:
            _json_guard(child, depth + 1)
        return
    if isinstance(value, UUID | StrEnum):
        return
    raise ValueError(f"CONTEXT_JSON_UNSUPPORTED:{type(value).__name__}")


def _jsonable(value: Any) -> Any:
    _json_guard(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(value[key]) for key in sorted(value)}
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    if isinstance(value, UUID | StrEnum):
        return str(value)
    return value
