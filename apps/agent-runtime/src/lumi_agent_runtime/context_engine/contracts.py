from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID


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
    TASK_INPUT = "TASK_INPUT"
    TASK_OUTPUT = "TASK_OUTPUT"
    ASSET = "ASSET"
    ARTIFACT = "ARTIFACT"
    RESEARCH = "RESEARCH"
    MEMORY = "MEMORY"
    SKILL = "SKILL"
    TOOL_RESULT = "TOOL_RESULT"


class TrustLevel(StrEnum):
    TRUSTED_SYSTEM = "TRUSTED_SYSTEM"
    TRUSTED_PROJECT = "TRUSTED_PROJECT"
    UNTRUSTED_RETRIEVED = "UNTRUSTED_RETRIEVED"


@dataclass(frozen=True, slots=True)
class ContextSourceRef:
    source_type: str
    source_id: str
    version: str
    content_hash: str

    def __post_init__(self) -> None:
        if not self.source_type or not self.source_id or not self.version:
            raise ValueError("CONTEXT_SOURCE_REF_INVALID")
        if len(self.content_hash) < 32:
            raise ValueError("CONTEXT_SOURCE_HASH_INVALID")


@dataclass(frozen=True, slots=True)
class ContextItem:
    item_id: str
    layer: ContextLayer
    kind: ContextKind
    content: str
    source: ContextSourceRef
    trust: TrustLevel
    priority: int = 100
    token_estimate: int = 0
    relevance_score: float = 0.0
    freshness: float = 0.0
    pinned: bool = False
    permissions: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.item_id or not self.content:
            raise ValueError("CONTEXT_ITEM_INVALID")
        if not 0 <= self.relevance_score <= 1 or not 0 <= self.freshness <= 1:
            raise ValueError("CONTEXT_ITEM_SCORE_INVALID")
        if self.token_estimate < 0:
            raise ValueError("CONTEXT_ITEM_TOKEN_ESTIMATE_INVALID")


@dataclass(frozen=True, slots=True)
class LayerBudget:
    layer: ContextLayer
    max_tokens: int
    required: bool = False

    def __post_init__(self) -> None:
        if self.max_tokens < 1:
            raise ValueError("CONTEXT_LAYER_BUDGET_INVALID")


@dataclass(frozen=True, slots=True)
class ContextRequest:
    organization_id: UUID
    project_id: UUID
    agent_run_id: UUID
    task_id: UUID | None
    agent_ref: str
    purpose: str
    query: str
    max_input_tokens: int
    response_reserve_tokens: int
    layer_budgets: tuple[LayerBudget, ...]
    retrieval_limit: int = 12
    required_source_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.agent_ref or not self.purpose:
            raise ValueError("CONTEXT_REQUEST_IDENTITY_INVALID")
        if self.max_input_tokens < 256 or self.response_reserve_tokens < 1:
            raise ValueError("CONTEXT_REQUEST_BUDGET_INVALID")
        if self.context_budget_tokens < 128:
            raise ValueError("CONTEXT_REQUEST_CONTEXT_BUDGET_TOO_SMALL")
        if not 1 <= self.retrieval_limit <= 100:
            raise ValueError("CONTEXT_RETRIEVAL_LIMIT_INVALID")
        layers = [item.layer for item in self.layer_budgets]
        if len(layers) != len(set(layers)):
            raise ValueError("CONTEXT_LAYER_BUDGET_DUPLICATE")

    @property
    def context_budget_tokens(self) -> int:
        return self.max_input_tokens - self.response_reserve_tokens

    @property
    def semantic_hash(self) -> str:
        payload = {
            "organization_id": str(self.organization_id), "project_id": str(self.project_id),
            "agent_run_id": str(self.agent_run_id), "task_id": str(self.task_id) if self.task_id else None,
            "agent_ref": self.agent_ref, "purpose": self.purpose, "query": self.query,
            "context_budget_tokens": self.context_budget_tokens,
            "layer_budgets": [{"layer": x.layer.value, "max_tokens": x.max_tokens, "required": x.required} for x in self.layer_budgets],
            "retrieval_limit": self.retrieval_limit, "required_source_ids": sorted(self.required_source_ids), "metadata": self.metadata,
        }
        return _hash(payload)


@dataclass(frozen=True, slots=True)
class ContextManifest:
    request_hash: str
    items: tuple[ContextItem, ...]
    total_tokens: int
    max_tokens: int
    source_versions: tuple[str, ...]
    cache_key: str
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.total_tokens < 0 or self.total_tokens > self.max_tokens:
            raise ValueError("CONTEXT_MANIFEST_BUDGET_INVALID")

    @property
    def freeze_hash(self) -> str:
        return _hash({
            "request_hash": self.request_hash,
            "items": [{"item_id": x.item_id, "layer": x.layer.value, "kind": x.kind.value, "source": asdict(x.source), "trust": x.trust.value, "priority": x.priority, "token_estimate": x.token_estimate, "relevance_score": x.relevance_score, "content_hash": hashlib.sha256(x.content.encode()).hexdigest()} for x in self.items],
            "total_tokens": self.total_tokens, "max_tokens": self.max_tokens, "source_versions": self.source_versions, "cache_key": self.cache_key, "warnings": self.warnings,
        })


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
