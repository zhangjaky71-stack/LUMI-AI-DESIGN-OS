from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .bootstrap import (
    load_bootstrap_catalog,
    load_named_catalog,
    load_skill_catalog,
)
from .definition import AgentDefinition
from .dependencies import (
    CatalogEntry,
    DependencyResolver,
    Node23ModelPolicyCatalog,
    Node25ToolCatalog,
    StaticNamedCatalog,
    StaticVersionedCatalog,
)
from .errors import (
    AgentDefinitionInvalidError,
    AgentDefinitionNotFoundError,
    AgentDependencyError,
    AgentPromptPolicyError,
    AgentProvenanceConflictError,
    AgentRegistryError,
    AgentReleaseError,
    AgentVersionConflictError,
    AgentVersionResolutionError,
)
from .loader import load_definition, load_definitions, load_release_manifest
from .postgres_store import PostgresAgentRunProvenanceStore
from .provenance import AgentProvenance, ResolvedAgent, ResolvedDependency
from .registry import AgentRegistry
from .release import AgentReleaseManager, EvalEvidence, EvalReleaseGate
from .release_types import AgentReleaseManifest, AgentReleaseRecord, AgentReleaseStatus
from .requirements import MemoryPolicy, SkillRequirement, ToolRequirement
from .semver import SemVer, matches, select_highest
from .validator import AgentValidator, StaticSystemPromptLinter

if TYPE_CHECKING:
    from .deep_adapter import to_deep_agent_definition as to_deep_agent_definition

__all__ = [
    "AgentDefinition",
    "AgentDefinitionInvalidError",
    "AgentDefinitionNotFoundError",
    "AgentDependencyError",
    "AgentPromptPolicyError",
    "AgentProvenance",
    "AgentProvenanceConflictError",
    "AgentRegistry",
    "AgentRegistryError",
    "AgentReleaseError",
    "AgentReleaseManager",
    "AgentReleaseManifest",
    "AgentReleaseRecord",
    "AgentReleaseStatus",
    "AgentValidator",
    "AgentVersionConflictError",
    "AgentVersionResolutionError",
    "CatalogEntry",
    "DependencyResolver",
    "EvalEvidence",
    "EvalReleaseGate",
    "MemoryPolicy",
    "Node23ModelPolicyCatalog",
    "Node25ToolCatalog",
    "PostgresAgentRunProvenanceStore",
    "ResolvedAgent",
    "ResolvedDependency",
    "SemVer",
    "SkillRequirement",
    "StaticNamedCatalog",
    "StaticSystemPromptLinter",
    "StaticVersionedCatalog",
    "ToolRequirement",
    "load_bootstrap_catalog",
    "load_definition",
    "load_definitions",
    "load_named_catalog",
    "load_release_manifest",
    "load_skill_catalog",
    "matches",
    "select_highest",
    "to_deep_agent_definition",
]


def __getattr__(name: str) -> Any:
    if name == "to_deep_agent_definition":
        from .deep_adapter import to_deep_agent_definition

        return to_deep_agent_definition
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
