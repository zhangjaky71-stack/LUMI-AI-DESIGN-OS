from __future__ import annotations


class AgentRegistryError(RuntimeError):
    code = "AGENT_REGISTRY_ERROR"


class AgentDefinitionNotFoundError(AgentRegistryError):
    code = "AGENT_DEFINITION_NOT_FOUND"


class AgentDefinitionInvalidError(AgentRegistryError):
    code = "AGENT_DEFINITION_INVALID"


class AgentVersionConflictError(AgentRegistryError):
    code = "AGENT_VERSION_CONFLICT"


class AgentVersionResolutionError(AgentRegistryError):
    code = "AGENT_VERSION_RESOLUTION_FAILED"


class AgentDependencyError(AgentRegistryError):
    code = "AGENT_DEPENDENCY_INVALID"


class AgentReleaseError(AgentRegistryError):
    code = "AGENT_RELEASE_INVALID"


class AgentPromptPolicyError(AgentRegistryError):
    code = "AGENT_PROMPT_POLICY_INVALID"


class AgentProvenanceConflictError(AgentRegistryError):
    code = "AGENT_PROVENANCE_CONFLICT"
